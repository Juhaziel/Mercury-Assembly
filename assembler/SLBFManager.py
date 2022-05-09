import struct, sys, os, getopt

def wordsToBytes(words):
    v = []
    for word in words: v.extend([(word >> 8) & 0xFF, word & 0xFF])
    return bytes(v)

def bytesToWords(bytes):
    if len(bytes) % 2 != 0: raise Exception("Cannot convert an odd about of bytes to words.")
    return [(bytes[i] << 8) | bytes[i+1] for i in range(0, len(bytes), 2)]

def packedWordStrToStr(words):
    str = ""
    for word in words:
        word &= 0xFFFF
        c1 = chr(word >> 8)
        c2 = chr(word & 0xFF)
        if not c1.isascii() or not c2.isascii(): raise Exception("Cannot convert word sequence to ASCII string.")
        if c1 != "\0": str += c1
        str += c2
    return str

def strToPackedWordStr(str):
    if not str.isascii(): raise Exception("Non-ASCII strings are not supported.")
    words = []
    for i in range(0, len(str)-1, 2):
        words.append((ord(str[i]) << 8) | ord(str[i+1]))
    if len(str) % 2 != 0: words.append(ord(str[-1]))
    return words

class GeneralSection:
    def __init__(self, words=None):
        if not words: words = []
        self.words = []
        self.words.extend(words)
    
    def getSize(self):
        return len(self.words)
    
    @classmethod
    def serializeBytes(cls, section):
        return wordsToBytes(section.words)
    
    @classmethod
    def serializeWords(cls, section):
        return section.words
    
    @classmethod
    def deserializeBytes(cls, bytes):
        return GeneralSection(bytesToWords(bytes))
    
    @classmethod
    def deserializeWords(cls, words):
        return GeneralSection(words)        

class Relocation:
    ENTRYSIZE = 4
    
    def __init__(self, r_offset, r_symndx):
        self.r_offset = r_offset & 0xFFFFFFFF
        self.r_symndx = r_symndx & 0xFFFFFFFF
        self.tempndx = 0 # Needed for linking. Not saved in the file.
    
    @classmethod
    def serializeBytes(cls, reloc):
        s = struct.pack(">4H",
                        reloc.r_offset & 0xFFFF,
                        (reloc.r_offset >> 16) & 0xFFFF,
                        reloc.r_symndx & 0xFFFF,
                        (reloc.r_symndx >> 16) & 0xFFFF
        )
        return s
    
    @classmethod
    def serializeWords(cls, reloc):
        return bytesToWords(cls.serializeBytes(reloc))
    
    @classmethod
    def deserializeBytes(cls, bytes):
        if len(bytes) != 2*cls.ENTRYSIZE: raise Exception("Invalid number of bytes for relocation.")
        r_offsetlo, r_offsethi, r_symndxlo, r_symndxhi = struct.unpack(">4H", bytes)
        reloc = Relocation((r_offsethi << 16) | r_offsetlo,
                           (r_symndxhi << 16) | r_symndxlo
        )
        return reloc
    
    @classmethod
    def deserializeWords(cls, words):
        if len(words) != cls.ENTRYSIZE: raise Exception("Invalid number of words for relocation.")
        return cls.deserializeBytes(wordsToBytes(words))

class RelocTable:
    def __init__(self, relocs=None):
        if not relocs: relocs = []
        self.relocs = []
        self.relocs.extend(relocs)
    
    def getSize(self):
        return Relocation.ENTRYSIZE * len(self.relocs)
    
    def getRelocByID(self, id):
        return self.relocs[id]
    
    def getRelocIDsBySymbolID(self, symid):
        relocs = []
        for reloc in self.relocs:
            if reloc.r_symndx == symid: relocs.append(reloc)
        return relocs
    
    def getIDByReloc(self, reloc):
        if not reloc in self.relocs: return None
        return self.relocs.index(reloc)       
    
    @classmethod
    def serializeBytes(cls, reltab):
        s = bytearray()
        for reloc in reltab.relocs:
            s.extend(Relocation.serializeBytes(reloc))
        return s
    
    @classmethod
    def serializeWords(cls, reltab):
        return bytesToWords(cls.serializeBytes(reltab))
    
    @classmethod
    def deserializeBytes(cls, bytes):
        if len(bytes) % (2*Relocation.ENTRYSIZE): raise Exception("Invalid number of bytes for Relocation Table")
        return RelocTable([Relocation.deserializeBytes(bytes[i:i+2*Relocation.ENTRYSIZE]) for i in range(0, len(bytes), 2*Relocation.ENTRYSIZE)])
    
    @classmethod
    def deserializeWords(cls, words):
        return cls.deserializeBytes(wordsToBytes(words))

class StringTable:
    def __init__(self, pStrings=None):
        if not pStrings: pStrings = []
        self.pStrings = []
        if len(pStrings) == 0 or pStrings[0] != 0: self.pStrings = [0]
        self.pStrings.extend(pStrings)
        if self.pStrings[-1] != 0: self.pStrings.append(0)
    
    def getSize(self):
        return len(self.pStrings)
    
    def getStringByID(self, id):
        pString = []
        i = id
        while self.pStrings[i] != 0:
            pString.append(self.pStrings[i])
            i += 1
        return packedWordStrToStr(pString)

    def getIDByString(self, string):
        pMatch = strToPackedWordStr(string)
        pString = []
        id = i = 0
        while i < len(self.pStrings):
            if self.pStrings[i] == 0:
                if pString == pMatch: return id
                pString = []
                id = i + 1
            else:
                pString.append(self.pStrings[i])
            i += 1
        self.pStrings.extend(pMatch)
        self.pStrings.append(0)
        return id
    
    def containsString(self, string):
        pMatch = strToPackedWordStr(string)
        pString = []
        i = 0
        while i < len(self.pStrings):
            if self.pStrings[i] == 0:
                if pString == pMatch: return True
                pString = []
            else:
                pString.append(self.pStrings[i])
            i += 1
        return False

    @classmethod
    def serializeBytes(cls, strtab):
        return wordsToBytes(cls.serializeWords(strtab))
    
    @classmethod
    def serializeWords(cls, strtab):
        return strtab.pStrings
    
    @classmethod
    def deserializeBytes(cls, bytes):
        return cls.deserializeWords(bytesToWords(bytes))
    
    @classmethod
    def deserializeWords(cls, words):
        return StringTable(words)

class Symbol:
    ENTRYSIZE = 8
    SINFO_LOCAL  = 0
    SINFO_GLOBAL = 1
    SINFO_WEAK   = 2
    SINFO_EXTERN = 3
    SDEF_UNDEF = 0
    SDEF_ABS = 0xFFFF
    
    def __init__(self, s_name, s_value, s_info, s_shndx):
        self.s_name = s_name & 0xFFFFFFFF
        self.s_value = s_value & 0xFFFFFFFF
        self.s_info = s_info & 0xFFFF
        self.s_shndx = s_shndx & 0xFFFF
    
    @classmethod
    def serializeBytes(cls, symbol):
        s = struct.pack(">8H",
                        symbol.s_name & 0xFFFF, (symbol.s_name >> 16) & 0xFFFF,
                        symbol.s_value & 0xFFFF, (symbol.s_value >> 16) & 0xFFFF,
                        symbol.s_info,
                        symbol.s_shndx,
                        0, 0
        )
        return s
    
    @classmethod
    def serializeWords(cls, symbol):
        return bytesToWords(cls.serializeBytes(symbol))
    
    @classmethod
    def deserializeBytes(cls, bytes):
        if len(bytes) != 2*cls.ENTRYSIZE: raise Exception("Invalid number of bytes for symbol.")
        s_namelo, s_namehi, s_valuelo, s_valuehi, s_info, s_shndx, _PADDING0, _PADDING1 = struct.unpack(">8H", bytes)
        if _PADDING0 != 0 or _PADDING1 != 0: print("[WARNING] Padding bytes are not 0.")
        symbol = Symbol((s_namehi << 16) | s_namelo,
                        (s_valuehi << 16) | s_valuelo,
                        s_info,
                        s_shndx
        )
        return symbol
    
    @classmethod
    def deserializeWords(cls, words):
        if len(words) != cls.ENTRYSIZE: raise Exception("Invalid number of words for symbol.")
        return cls.deserializeBytes(wordsToBytes(words))

class SymbolTable:
    def __init__(self, symbols=None):
        if not symbols: symbols = []
        self.symbols = []
        self.symbols.extend(symbols)
    
    def getSize(self):
        return Symbol.ENTRYSIZE * len(self.symbols)
    
    def getSymbolByID(self, id):
        return self.symbols[id]
    
    def addSymbol(self, file, symbol, addWithName=True):
        id = len(self.symbols)
        self.symbols.append(symbol)
        if addWithName:
            symtab_header, _ = file.getSection(file.header.h_symtabndx)
            _, hashtab = file.getSection(file.header.h_hashtabndx)
            _, symstrtab = file.getSection(symtab_header.sh_link)
            hashtab.addSymbolIDByName(symstrtab.getStringByID(symbol.s_name), id)
            file.rehash()
        return id
    
    def getIDBySymbol(self, symbol):
        if not symbol in self.symbols: return 0
        return self.symbols.index(symbol)
    
    @classmethod
    def serializeBytes(cls, symtab):
        s = bytearray()
        for symbol in symtab.symbols:
            s.extend(Symbol.serializeBytes(symbol))
        return s
    
    @classmethod
    def serializeWords(cls, symtab):
        return bytesToWords(cls.serializeBytes(symtab))
    
    @classmethod
    def deserializeBytes(cls, bytes):
        if len(bytes) % (2*Symbol.ENTRYSIZE) != 0: raise Exception("Invalid number of bytes for Symbol Table")
        return SymbolTable([Symbol.deserializeBytes(bytes[i:i+2*Symbol.ENTRYSIZE]) for i in range(0, len(bytes), 2*Symbol.ENTRYSIZE)])
    
    @classmethod
    def deserializeWords(cls, words):
        return cls.deserializeBytes(wordsToBytes(words))

class HashTable:
    @classmethod
    def _hashSymbol(cls, str):
        if not str.isascii(): raise Exception("Non-ASCII strings are not supported in HashTable.")
        hash = 3911
        for c in bytes(str, "ascii"): hash = (31*hash+c) & 0xFFFF
        return hash
    
    @classmethod
    def _getSymbolNameByID(cls, file, symid):
        symtab_header, symtab = file.getSection(file.header.h_symtabndx)
        _, symstrtab = file.getSection(symtab_header.sh_link)
        return symstrtab.getStringByID(symtab.getSymbolByID(symid).s_name)
    
    def __init__(self, nbucket, nchain):
        if nbucket == 0: raise Exception("nbucket of Hash Table cannot be 0.")
        if nchain == 0: raise Exception("nchain of Hash Table cannot be 0.")
        self.nbucket = nbucket
        self.nchain = nchain
        self.bucket = [0]*nbucket
        self.chain = [0]*nchain
        self._occupied = 0
    
    def getLoadFactor(self):
        return self._occupied / self.nbucket
     
    def getSize(self):
        return 4 + 2*len(self.bucket) + 2*len(self.chain)

    def containsName(self, file, name):
        try:
            self.getSymbolIDByName(file, name)
            return True
        except Exception:
            return False
   
    def getSymbolIDByName(self, file, name):
        hash = HashTable._hashSymbol(name) % self.nbucket
        symid = self.bucket[hash]
        if symid == 0: raise Exception("No such symbol.")
        if HashTable._getSymbolNameByID(file, symid) == name: return symid
        i = 0
        while i < self.nchain:
            symid = self.chain[symid]
            if symid == 0: raise Exception("No such symbol.")
            if HashTable._getSymbolNameByID(file, symid) == name: return symid
            i += 1
        raise Exception("No such symbol.")

    def addSymbolIDByName(self, name, id):
        hash = HashTable._hashSymbol(name) % self.nbucket
        symid = self.bucket[hash]
        if symid == id: return
        if symid == 0:
            self.bucket[hash] = id
            self._occupied += 1
            return
        i = 0
        while i < self.nchain:
            o_symid = symid
            symid = self.chain[o_symid]
            if symid == id: return
            if symid == 0:
                self.chain[o_symid] = id
                return
            i += 1
        raise Exception("No space left in hash table.")
    
    @classmethod
    def serializeBytes(cls, hashtab):
        s = bytearray(struct.pack(">4H",
                                  hashtab.nbucket & 0xFFFF, (hashtab.nbucket >> 16) & 0xFFFF,
                                  hashtab.nchain & 0xFFFF, (hashtab.nchain >> 16) & 0xFFFF
        ))
        for bucket in hashtab.bucket:
            s.extend(struct.pack(">2H", bucket & 0xFFFF, (bucket >> 16) & 0xFFFF))
        for chain in hashtab.chain:
            s.extend(struct.pack(">2H", chain & 0xFFFF, (chain >> 16) & 0xFFFF))
        return bytes(s)
    
    @classmethod
    def serializeWords(cls, hashtab):
        return bytesToWords(cls.serializeBytes(hashtab))
    
    @classmethod
    def deserializeBytes(cls, bytes):
        nbucketlo, nbuckethi, nchainlo, nchainhi = struct.unpack(">4H", bytes[0:8])
        nbucket = (nbuckethi << 16) | nbucketlo
        nchain = (nchainhi << 16) | nchainlo
        hashtab = HashTable(nbucket, nchain)
        if len(bytes) != 2*hashtab.getSize(): raise Exception("Invalid number of bytes for Hash Table.")
        for i in range(nbucket):
            bucketlo, buckethi = struct.unpack(">2H", bytes[8+4*i:12+4*i])
            hashtab.bucket[i] = (buckethi << 16) | bucketlo
        for i in range(nchain):
            chainlo, chainhi = struct.unpack(">2H", bytes[8+2*(nbucket+2*i):12+2*(nbucket+2*i)])
            hashtab.chain[i] = (chainhi << 16) | chainlo
        return hashtab
    
    @classmethod
    def deserializeWords(cls, words):
        return cls.deserializeBytes(wordsToBytes(words))

class SectionHeader:
    ENTRYSIZE      = 16
    
    SHTYPE_INV     = 0
    SHTYPE_PROGDAT = 1
    SHTYPE_NOBITS  = 2
    SHTYPE_SYMTAB  = 3
    SHTYPE_STRTAB  = 4
    SHTYPE_RELTAB  = 5
    SHTYPE_HASHTAB = 6
    
    def __init__(self, sh_name, sh_type, sh_addr, sh_offset, sh_size, sh_link, sh_alval, sh_align, sh_entsize):
        if not (0 <= sh_type <= 6): print("[WARNING] Unknown section type \""+sh_type+"\"")
        self.sh_name = sh_name & 0xFFFFFFFF
        self.sh_type = sh_type & 0xFFFF
        self.sh_addr = sh_addr & 0xFFFFFFFF
        self.sh_offset = sh_offset & 0xFFFFFFFF
        self.sh_size = sh_size & 0xFFFFFFFF
        self.sh_link = sh_link & 0xFFFFFFFF
        self.sh_alval = sh_alval & 0xFFFF
        self.sh_align = sh_align & 0xFFFF
        self.sh_entsize = sh_entsize & 0xFFFF
    
    @classmethod
    def serializeBytes(cls, header):
        s = struct.pack(">16H",
                        header.sh_name & 0xFFFF, (header.sh_name >> 16) & 0xFFFF,
                        header.sh_type,
                        header.sh_addr & 0xFFFF, (header.sh_addr >> 16) & 0xFFFF,
                        header.sh_offset & 0xFFFF, (header.sh_offset >> 16) & 0xFFFF,
                        header.sh_size & 0xFFFF, (header.sh_size >> 16) & 0xFFFF,
                        header.sh_link & 0xFFFF, (header.sh_link >> 16) & 0xFFFF,
                        header.sh_alval,
                        header.sh_align,
                        header.sh_entsize,
                        0, 0 # PADDING
                       )
        return s
    
    @classmethod
    def serializeWords(cls, header):
        return bytesToWords(cls.serializeBytes(header))
    
    @classmethod
    def deserializeBytes(cls, bytes):
        if len(bytes) != 2*cls.ENTRYSIZE: raise Exception("Invalid number of bytes for SLBF Header.")
        sh_namelo, sh_namehi, sh_type, sh_addrlo, sh_addrhi, sh_offsetlo, sh_offsethi, sh_sizelo, sh_sizehi = struct.unpack(">9H", bytes[0:18])
        sh_linklo, sh_linkhi, sh_alval, sh_align, sh_entsize, _PADDING0, _PADDING1 = struct.unpack(">7H", bytes[18:])
        if _PADDING0 != 0 or _PADDING1 != 0: print("[WARNING] Padding words are not 0.")
        header = SectionHeader((sh_namehi << 16) | sh_namelo,
                               sh_type,
                               (sh_addrhi << 16) | sh_addrlo,
                               (sh_offsethi << 16) | sh_offsetlo,
                               (sh_sizehi << 16) | sh_sizelo,
                               (sh_linkhi << 16) | sh_linklo,
                               sh_alval,
                               sh_align,
                               sh_entsize)
        return header        
    
    @classmethod
    def deserializeWords(cls, words):
        if len(words) != SLBFHeader.h_shentsize: raise Exception("Invalid number of words for Section Header.")
        return cls.deserializeBytes(wordsToBytes(words))

class SLBFHeader:
    h_ident = bytes("SLBF\r\n", "ascii") # Magic number
    h_hsize = 16
    h_shentsize = SectionHeader.ENTRYSIZE
    
    HTYPE_INV = 0
    HTYPE_OBJ = 1
    HTYPE_EXE = 2
    HVERS_INV = 0
    HVERS_CUR = h_version = 1
    
    def __init__(self, h_type, h_entry, h_shoff, h_shnum, h_shstrndx, h_symtabndx, h_hashtabndx):
        self.h_type = h_type & 0xFFFF
        self.h_entry = h_entry & 0xFFFFFFFF
        self.h_shoff = h_shoff & 0xFFFFFFFF
        self.h_shnum = h_shnum & 0xFFFF
        self.h_shstrndx = h_shstrndx & 0xFFFF
        self.h_symtabndx = h_symtabndx & 0xFFFF
        self.h_hashtabndx = h_hashtabndx & 0xFFFF
    
    @classmethod
    def serializeBytes(cls, header):
        s = struct.pack(">6s13H",
                                 cls.h_ident,
                                 header.h_type,
                                 cls.HVERS_CUR,
                                 header.h_entry & 0xFFFF, (header.h_entry >> 16) & 0xFFFF,
                                 header.h_shoff & 0xFFFF, (header.h_shoff >> 16) & 0xFFFF,
                                 cls.h_hsize,
                                 cls.h_shentsize,
                                 header.h_shnum,
                                 header.h_shstrndx & 0xFFFF,
                                 header.h_symtabndx & 0xFFFF,
                                 header.h_hashtabndx & 0xFFFF,
                                 0
        )
        return s
    
    @classmethod
    def serializeWords(cls, header):
        return bytesToWords(cls.serializeBytes(header))
    
    @classmethod
    def deserializeBytes(cls, bytes):
        if len(bytes) != 2*cls.h_hsize: raise Exception("Invalid number of bytes.")
        h_ident, h_type, h_version, h_entrylo, h_entryhi, h_shofflo, h_shoffhi, h_hsize, h_hshentsize, h_shnum = struct.unpack(">6s9H", bytes[0:24])
        h_strndx, h_symtabndx, h_hashtabndx, _PADDING = struct.unpack(">4H", bytes[24:])
        if h_ident != cls.h_ident: raise Exception("Magic numbers do not match.")
        if h_version != cls.HVERS_CUR: raise Exception("Version number does not match.")
        if _PADDING != 0: print("[WARNING] Padding word is not 0.")
        header = SLBFHeader(h_type,
                            (h_entryhi << 16) | h_entrylo,
                            (h_shoffhi << 16) | h_shofflo,
                            h_shnum,
                            h_strndx,
                            h_symtabndx,
                            h_hashtabndx
        )
        return header
    
    @classmethod
    def deserializeWords(cls, words):
        if len(words) != cls.h_hsize: raise Exception("Invalid number of words for SLBF Header.")
        return cls.deserializeBytes(wordsToBytes(words))

class SLBFManager:
    def __init__(self, h_type):
        self.header = SLBFHeader(h_type, 0, 0, 1, 0, 0, 0)
        self.sht = []
        self.sections = []
    
    @classmethod
    def newFile(cls, h_type):
        file = cls(h_type)
        file.addSection(SectionHeader(0, 0, 0, 0, 0, 0, 0, 0, 0), GeneralSection()) # undefined section 0
        
        shstrtab_header = SectionHeader(1, SectionHeader.SHTYPE_STRTAB, 0, -1, -1, 0, 0, 0, 0)
        shstrtab = StringTable(strToPackedWordStr("@shstrtab"))
        file.header.h_shstrndx = file.addSection(shstrtab_header, shstrtab) # Section name string table
                
        hashtab_header = SectionHeader(shstrtab.getIDByString("@hashtab"), SectionHeader.SHTYPE_HASHTAB, 0, -1, -1, 0, 0, 0, 2)
        hashtab = HashTable(4, 1)
        file.header.h_hashtabndx = file.addSection(hashtab_header, hashtab) # Hash table
        
        symtab_header = SectionHeader(shstrtab.getIDByString("@symtab"), SectionHeader.SHTYPE_SYMTAB, 0, -1, -1, -1, 0, 0, Symbol.ENTRYSIZE)
        symtab = SymbolTable()
        file.header.h_symtabndx = file.addSection(symtab_header, symtab) # Symbol table
        
        symstrtab_header = SectionHeader(shstrtab.getIDByString("@symstrtab"), SectionHeader.SHTYPE_STRTAB, 0, -1, -1, 0, 0, 0, 0)
        symstrtab = StringTable()
        symtab_header.sh_link = file.addSection(symstrtab_header, symstrtab) # Symbol string table
        
        symtab.addSymbol(file, Symbol(0, 0, 0, Symbol.SDEF_ABS))
        
        return file
    
    def rehash(self):
        _, hashtab = self.getSection(self.header.h_hashtabndx)
        symtab_header, symtab = self.getSection(self.header.h_symtabndx)
        _, symstrtab = self.getSection(symtab_header.sh_link)
                
        if hashtab.nchain < len(symtab.symbols):
            hashtab.chain.extend([0]*(len(symtab.symbols)-hashtab.nchain))
            hashtab.nchain = len(hashtab.chain)
        if hashtab.getLoadFactor() > 0.75:
            hashtab.bucket = [0]*int(hashtab.nbucket * 1.5)
            hashtab.nbucket = len(hashtab.bucket)
            hashtab.chain = [0]*hashtab.nchain
            for i in range(len(symtab.symbols)):
                symbol = symtab.symbols[i]
                symname = symstrtab.getStringByID(symbol.s_name)
                hashtab.addSymbolIDByName(symname, i)
    
    def getSection(self, id):
        return self.sht[id], self.sections[id]
    
    def getIDByHeader(self, sht):
        if not sht in self.sht: return 0
        return self.sht.index(sht)
    
    def getIDBySection(self, section):
        if not section in self.sections: return 0
        return self.sections.index(section)
    
    def addSection(self, s_header, section):
        self.sht.append(s_header)
        self.sections.append(section)
        if len(self.sht) != len(self.sections): raise Exception("Mismatch in Section Header Table and Section Table size.")
        self.header.h_shnum = len(self.sht)
        return len(self.sht)-1
    
    @classmethod
    def serializeBytes(cls, file):
        SLBFHeader.serializeBytes(file.header)
        s = bytearray()
        for i in range(file.header.h_shnum):
            s_header, section = file.getSection(i)
            s_header.sh_offset = len(s)//2 + SLBFHeader.h_hsize
            s_header.sh_size = section.getSize()
            if s_header.sh_type != SectionHeader.SHTYPE_NOBITS:
                s.extend(section.__class__.serializeBytes(section))
        file.header.h_shoff = len(s)//2 + SLBFHeader.h_hsize
        s2 = bytearray(SLBFHeader.serializeBytes(file.header))
        s2.extend(s)
        s = s2
        for s_header in file.sht:
            s.extend(SectionHeader.serializeBytes(s_header))
        return bytes(s)
    
    @classmethod
    def serializeWords(cls, file):
        return bytesToWords(cls.serializeBytes(file))
    
    @classmethod
    def deserializeBytes(cls, bytes):
        file = SLBFManager(0)
        file.header = SLBFHeader.deserializeBytes(bytes[0:2*SLBFHeader.h_hsize])
        for i in range(file.header.h_shnum):
            addr = file.header.h_shoff + i * file.header.h_shentsize
            s_header = SectionHeader.deserializeBytes(bytes[2*addr:2*(addr+file.header.h_shentsize)])
            if s_header.sh_type == SectionHeader.SHTYPE_NOBITS:
                file.addSection(s_header, GeneralSection())
                continue
            data = bytes[2*s_header.sh_offset:2*(s_header.sh_offset+s_header.sh_size)]
            if s_header.sh_type == SectionHeader.SHTYPE_INV: sh_type = GeneralSection
            elif s_header.sh_type == SectionHeader.SHTYPE_PROGDAT: sh_type = GeneralSection
            elif s_header.sh_type == SectionHeader.SHTYPE_SYMTAB: sh_type = SymbolTable
            elif s_header.sh_type == SectionHeader.SHTYPE_STRTAB: sh_type = StringTable
            elif s_header.sh_type == SectionHeader.SHTYPE_RELTAB: sh_type = RelocTable
            elif s_header.sh_type == SectionHeader.SHTYPE_HASHTAB: sh_type = HashTable
            else: raise Exception("Unknown section type \""+s_header.sh_type+"\"")
            file.addSection(s_header, sh_type.deserializeBytes(data))
        return file
    
    @classmethod
    def deserializeWords(cls, words):
        return cls.deserializeBytes(wordsToBytes(words))

def decode(in_filepath):
    print("[FILE] "+in_filepath)
    with open(in_filepath, "rb") as f:
        file = SLBFManager.deserializeBytes(f.read())
    print("[HEADER]")
    if file.header.h_type == SLBFHeader.HTYPE_INV: print("\tFTYPE:\t\t0 (INVALID)")
    elif file.header.h_type == SLBFHeader.HTYPE_OBJ: print("\tFTYPE:\t\t1 (OBJECT)")
    elif file.header.h_type == SLBFHeader.HTYPE_EXE: print("\tFTYPE:\t\t2 (EXECUTABLE)")
    print("\tVERS:\t\t"+str(file.header.h_version))
    print("\tENTRY:\t\t"+str(file.header.h_entry))
    print("\tSHT OFFSET:\t+{0} (+0x{0:X})".format(file.header.h_shoff))
    print("\tSHNUM:\t\t"+str(file.header.h_shnum))
    print("\tSHSTRTAB:\t"+str(file.header.h_shstrndx))
    print("\tSYMTAB:\t\t"+str(file.header.h_symtabndx))
    print("\tSYMHASHTAB:\t"+str(file.header.h_hashtabndx))
    
    SHSTRTAB_HDR, SHSTRTAB = file.getSection(file.header.h_shstrndx)
    
    print("\n[SECTION HEADERS]")
    for i in range(file.header.h_shnum):
        hdr, section = file.getSection(i)
        print("\t{:<5} - {}".format(i, repr(SHSTRTAB.getStringByID(hdr.sh_name))))
        print("\t\tTYPE:\t{} ({})".format(hdr.sh_type, ["INVALID", "PROGDAT", "NOBITS", "SYMTAB", "STRTAB", "RELTAB", "HASHTAB"][hdr.sh_type]))
        if hdr.sh_type in [SectionHeader.SHTYPE_PROGDAT, SectionHeader.SHTYPE_NOBITS]:
            print("\t\tVADDR:\t0x{:08X}".format(hdr.sh_addr))
        print("\t\tOFFSET:\t+{0} (+0x{0:X})".format(hdr.sh_offset))
        print("\t\tSIZE:\t{0} W (0x{0:X} W)".format(hdr.sh_size))
        if hdr.sh_link != 0:
            print("\t\tLINK:\t{:<5} - {}".format(hdr.sh_link, repr(SHSTRTAB.getStringByID(file.sht[hdr.sh_link].sh_name))))
        
        print()
    
    SYMTAB_HDR, SYMTAB = file.getSection(file.header.h_symtabndx)
    SYMSTRTAB_HDR, SYMSTRTAB = file.getSection(SYMTAB_HDR.sh_link)
    
    print("[SYMBOLS]")
    for i in range(len(SYMTAB.symbols)):
        symbol = SYMTAB.symbols[i]
        print("\t{:<5} - {}".format(i, repr(SYMSTRTAB.getStringByID(symbol.s_name))))
        print("\t\tTYPE:\t{} ({})".format(symbol.s_info, ["LOCAL", "GLOBAL", "WEAK", "EXTERN"][symbol.s_info]))
        if symbol.s_shndx == Symbol.SDEF_UNDEF:
            print("\t\tVALUE:\tUNDEF")
        elif symbol.s_shndx == Symbol.SDEF_ABS:
            print("\t\tVALUE:\t{0} (0x{0:X})".format(symbol.s_value))
        else:
            print("\t\tVADDR:\t{0} (0x{0:X})".format(symbol.s_value))
            print("\t\tSECT:\t{:<5} - {}".format(symbol.s_shndx, repr(SHSTRTAB.getStringByID(file.sht[symbol.s_shndx].sh_name))))
        
        print()
    
    print("[RELOCATIONS]")
    for i in range(file.header.h_shnum):
        hdr, section = file.getSection(i)
        if hdr.sh_type == SectionHeader.SHTYPE_RELTAB:
            print("{} - {}:".format(i, SHSTRTAB.getStringByID(hdr.sh_name)))
            linksect_hdr, _ = file.getSection(hdr.sh_link)
            print("\tSECTION:\t{} - {}".format(hdr.sh_link, SHSTRTAB.getStringByID(linksect_hdr.sh_name)))
            for v in range(len(section.relocs)):
                reloc = section.relocs[v]
                print("\tREL{}".format(v))
                print("\t\tVADDR:\t{} +0x{:X} (0x{:08X})".format(SHSTRTAB.getStringByID(linksect_hdr.sh_name), reloc.r_offset, linksect_hdr.sh_addr+reloc.r_offset))
                print("\t\tSYMBOL:\t{:<5} - {}".format(reloc.r_symndx, repr(SYMSTRTAB.getStringByID(SYMTAB.symbols[reloc.r_symndx].s_name))))
    
def main(argv):
    files = []
    for arg in argv:
        print("$ - Finding \""+arg+"\".")
        if not os.path.isfile(arg):
            print("[WARNING] \""+arg+"\" is not a file or does not exist.")
            continue
        files.append(arg)
    if len(files) == 0:
        print("[FATAL] No SLBF to read.")
        exit(-1)
    
    for in_filepath in files:
        try:
            decode(in_filepath)
        except Exception as e:
            print("[FATAL] Couldn't decode \""+in_filepath+"\" due to the following exception:")
            print(e)
            exit(-1)

if __name__ == "__main__":
    main(sys.argv[1:])
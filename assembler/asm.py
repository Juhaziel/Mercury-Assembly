import os, sys, getopt, math

from lexer import Lexer
from opdb import matchInst
from SLBFManager import *

verbose = False
outext = ".o"
outdir = ""

def wrap32bits(num):
    num %= 0xFFFFFFFF
    if num >= 0x80000000: return 0x100000000 - num
    else: return num

def reprMath(mop):
    if mop["type"] == "op":
        mop_str = ""
        for node in mop["nodes"]:
            mop_str += mop["op"] + reprMath(node)
        return mop_str[len(mop["op"]):]
    elif mop["type"] == "mexpr":
        return "{" + reprMath(mop["val"]) + "}"
    return str(mop["val"])

def reprOps(ops):
    if len(ops) == 0: return ""
    def reprOp(op):
        op_str = ""
        reg = ""
        imm = ""
        if op["rtype"] == "r16": reg = "%"+"ABCDEGMLXYSPUVFZ"[op["rval"]]
        elif op["rtype"] == "r32": reg = "%"+"ABCDEGMLXYSPUVFZ"[op["rval"]^0b0001]+"ABCDEGMLXYSPUVFZ"[op["rval"]]
        if op["itype"] == "abs": imm = str(op["ival"])
        elif op["itype"] == "lbl": imm = op["ival"]
        elif op["itype"] == "mexpr": imm = "{"+reprMath(op["ival"])+"}"
        if reg:
            if op["rtype"] == "r16" and (not imm or op["rval"] != 15): op_str = reg
            elif op["rtype"] == "r32": op_str = reg
            if imm: reg += "+"
        if imm: op_str += imm
        if op["ismem"]: op_str = "$("+op_str+")"
        return op_str
    out_str = ""
    for op in ops:
        out_str += reprOp(op) + ", "
    return out_str[:-2]

def assemble(in_filepath, out_dirpath):
    if verbose:
        print("[FILE] "+in_filepath)
        print("$ - Begin Lexer")
    lines = Lexer.lexfile(in_filepath)
    if verbose:
        for line in lines:
            line_str = str(line["ln"])+":\t"
            if line["label"]: line_str += line["label"]+": "
            if line["cmd"]:
                line_str += "\t" + line["cmd"]
                if line["ops"]: line_str += "\t" + reprOps(line["ops"])
            print(line_str)
        print("$ - End Lexer\n")
        print("$ - Begin Translation")
    file = SLBFManager.newFile(SLBFHeader.HTYPE_OBJ)
    
    SHSTRTAB_HDR, SHSTRTAB = file.getSection(file.header.h_shstrndx)
    HASHTAB_HDR, HASHTAB = file.getSection(file.header.h_hashtabndx)
    SYMTAB_HDR, SYMTAB = file.getSection(file.header.h_symtabndx)
    SYMSTRTAB_HDR, SYMSTRTAB = file.getSection(SYMTAB_HDR.sh_link)
    
    _ip = Symbol(SYMSTRTAB.getIDByString("@ip"), 0, Symbol.SINFO_LOCAL, Symbol.SDEF_ABS)
    SYMTAB.addSymbol(file, _ip)
    _sp = Symbol(SYMSTRTAB.getIDByString("@sp"), 0, Symbol.SINFO_LOCAL, Symbol.SDEF_ABS)
    SYMTAB.addSymbol(file, _sp)
    
    MEXPR_RELOCS = []
    CUR_SECTION_HDR, CUR_SECTION = None, None
    REL_SECTION_HDR, REL_SECTION = None, None
    
    def defSym(symname, value, section=None):
        if not section: section = file.getIDBySection(CUR_SECTION)
        if not section: raise Exception("Section must be defined when defining a symbol.")
        if HASHTAB.containsName(file, symname):
            symid = HASHTAB.getSymbolIDByName(file, symname)
            symbol = SYMTAB.getSymbolByID(symid)
            if symbol.s_shndx != Symbol.SDEF_UNDEF: raise Exception("Cannot redefine symbol \""+symname+"\".")
            if symbol.s_info == Symbol.SINFO_EXTERN: raise Exception("Cannot define external symbol \""+symname+"\"in the same file.")
            symbol.s_value = value
            symbol.s_shndx = section
            for i in range(file.header.h_shnum):
                header, rtab = file.getSection(i)
                if header.sh_type == SectionHeader.SHTYPE_RELTAB:
                    shdr, section = file.getSection(header.sh_link)
                    for reloc in rtab.relocs:
                        if reloc.r_symndx != symid: continue
                        section.words[reloc.r_offset] = (symbol.s_value) & 0xFFFF
                        section.words[reloc.r_offset+1] = ((symbol.s_value) >> 16) & 0xFFFF
                        
        else:
            symbol = Symbol(SYMSTRTAB.getIDByString(symname), value, Symbol.SINFO_LOCAL, section)
            SYMTAB.addSymbol(file, symbol)
        return symbol
    
    def defRel(symname, offset):
        nonlocal REL_SECTION_HDR, REL_SECTION
        if not CUR_SECTION: raise Exception("Section must be defined when defining a relocation.")
        if not REL_SECTION:
            REL_SECTION_HDR = SectionHeader(SHSTRTAB.getIDByString("@rel"+SHSTRTAB.getStringByID(CUR_SECTION_HDR.sh_name)),
                                            SectionHeader.SHTYPE_RELTAB,
                                            0, -1, -1, file.getIDBySection(CUR_SECTION), 0, 0, Relocation.ENTRYSIZE)
            REL_SECTION = RelocTable()
            file.addSection(REL_SECTION_HDR, REL_SECTION)
        if HASHTAB.containsName(file, symname):
            symid = HASHTAB.getSymbolIDByName(file, symname)
        else:
            symid = SYMTAB.addSymbol(file, Symbol(SYMSTRTAB.getIDByString(symname), 0, Symbol.SINFO_LOCAL, Symbol.SDEF_UNDEF))
        reloc = Relocation(offset, symid)
        REL_SECTION.relocs.append(reloc)
        return reloc

    def evalimm(ival):
        if isinstance(ival, int): return {"type": "abs", "val": ival}
        if isinstance(ival, str):
            if HASHTAB.containsName(file, ival):
                symbol = SYMTAB.getSymbolByID(HASHTAB.getSymbolIDByName(file, ival))
                if symbol.s_shndx != Symbol.SDEF_UNDEF:
                    return {"type": "abs", "val": symbol.s_value}
            return {"type": "lbl", "val": ival}
        if ival["type"] in ["abs", "lbl", "mexpr"]: return evalimm(ival["val"])
        if ival["type"] == "op":
            op = ival["op"]
            nodes = []
            isimm = True
            for node in ival["nodes"]:
                enode = evalimm(node)
                if enode["type"] != "abs": isimm = False
                nodes.append(enode)
            if not isimm: return {"type": "op", "op": op, "nodes": nodes}
            if op in "~":
                if len(nodes) != 1: raise Exception("Operator "+op+" expected 1 argument, got "+str(len(nodes)))
                op1 = nodes[0]["val"]
                if op == "~": val = -op1-1
                return {"type": "abs", "val": wrap32bits(val)}
            elif op in "+-*/%&|^<>":
                if len(nodes) != 2: raise Exception("Operator "+op+" expected 2 arguments, got "+str(len(nodes)))
                op1, op2 = nodes[0]["val"], nodes[1]["val"]
                if op == "+": val = op1 + op2
                elif op == "-": val = op1 - op2
                elif op == "*": val = op1 * op2
                elif op == "/": val = op1 // op2
                elif op == "%": val = op1 % op2
                elif op == "&": val = op1 & op2
                elif op == "|": val = op1 | op2
                elif op == "^": val = op1 ^ op2
                elif op == "<": val = 0xFFFFFFFF if wrap32bits(op1) < wrap32bits(op2) else 0
                elif op == ">": val = 0xFFFFFFFF if wrap32bits(op1) > wrap32bits(op2) else 0
                return {"type": "abs", "val": wrap32bits(val)}
            elif op in ["<<", ">>", "==", "~=", "<=", ">="]:
                if len(nodes) != 2: raise Exception("Operator "+op+" expected 2 arguments, got "+str(len(nodes)))
                op1, op2 = nodes[0]["val"], nodes[1]["val"]
                if op == "<<": val = op1 << op2
                elif op == ">>": val = op1 >> op2
                elif op == "==": val = 0xFFFFFFFF if wrap32bits(op1) == wrap32bits(op2) else 0
                elif op == "~=": val = 0xFFFFFFFF if wrap32bits(op1) != wrap32bits(op2) else 0
                elif op == "<=": val = 0xFFFFFFFF if wrap32bits(op1) <= wrap32bits(op2) else 0
                elif op == ">=": val = 0xFFFFFFFF if wrap32bits(op1) >= wrap32bits(op2) else 0
                return {"type": "abs", "val": wrap32bits(val)}
            else:
                raise Exception("Unknown operator \""+str(op)+"\".")
    
    for line in lines:
        try:
            if line["label"]: # If there is a label
                defSym(line["label"], _ip.s_value)
            if line["cmd"]:
                cmd = line["cmd"]
                if cmd == ".global":
                    for op in line["ops"]:
                        if op["rtype"]: raise Exception("Registers are not allowed in .global")
                        if op["ismem"]: raise Exception("Memory indexing is not allowed in .global")
                        if op["itype"] != "lbl": raise Exception(".global argument must be a label.")
                        if HASHTAB.containsName(file, op["ival"]):
                            symbol = SYMTAB.getSymbolByID(HASHTAB.getSymbolIDByName(file, op["ival"]))
                            if symbol.s_info != Symbol.SINFO_LOCAL: raise Exception("Symbol \""+op["ival"]+"\" already has a non-local visibility.")
                            symbol.s_info = Symbol.SINFO_GLOBAL
                        else:
                            symbol = Symbol(SYMSTRTAB.getIDByString(op["ival"]), 0, Symbol.SINFO_GLOBAL, Symbol.SDEF_UNDEF)
                            SYMTAB.addSymbol(file, symbol)
                elif cmd == ".weak":
                    for op in line["ops"]:
                        if op["rtype"]: raise Exception("Registers are not allowed in .weak")
                        if op["ismem"]: raise Exception("Memory indexing is not allowed in .weak")
                        if op["itype"] != "lbl": raise Exception(".weak argument must be a label.")
                        if HASHTAB.containsName(file, op["ival"]):
                            symbol = SYMTAB.getSymbolByID(HASHTAB.getSymbolIDByName(file, op["ival"]))
                            if symbol.s_info != Symbol.SINFO_LOCAL: raise Exception("Symbol \""+op["ival"]+"\" already has a non-local visibility.")
                            symbol.s_info = Symbol.SINFO_WEAK
                        else:
                            symbol = Symbol(SYMSTRTAB.getIDByString(op["ival"]), 0, Symbol.SINFO_WEAK, Symbol.SDEF_UNDEF)
                            SYMTAB.addSymbol(file, symbol)
                elif cmd == ".extern":
                    for op in line["ops"]:
                        if op["rtype"]: raise Exception("Registers are not allowed in .extern")
                        if op["ismem"]: raise Exception("Memory indexing is not allowed in .extern")
                        if op["itype"] != "lbl": raise Exception(".extern argument must be a label.")
                        if HASHTAB.containsName(file, op["ival"]): raise Exception("Defined symbol \""+op["ival"]+"\" cannot be set to extern visiblity.")
                        symbol = Symbol(SYMSTRTAB.getIDByString(op["ival"]), 0, Symbol.SINFO_EXTERN, Symbol.SDEF_UNDEF)
                        SYMTAB.addSymbol(file, symbol)
                elif cmd == ".set":
                    if len(line["ops"]) != 2: raise Exception(".set expected 2 arguments, got "+str(len(line["ops"]))+".")
                    name = line["ops"][0]
                    value = line["ops"][1]
                    if name["rtype"]: raise Exception(".set 1st argument cannot be a register.")
                    if name["ismem"]: raise Exception(".set 1st argument cannot be a memory reference.")
                    if name["itype"] != "lbl": raise Exception(".set 1st argument must be a label.")
                    if value["rtype"]: raise Exception(".set 2nd argument cannot be a register.")
                    if value["ismem"]: raise Exception(".set 2nd argument cannot be a memmory reference.")
                    value = evalimm(value["ival"])
                    if value["type"] != "abs": raise Exception(".set 2nd argument must be immediate or mexpr with all labels defined.")
                    defSym(name["ival"], value["val"], Symbol.SDEF_ABS)
                elif cmd == ".string":
                    if not CUR_SECTION: raise Exception("Section must be defined when writing data.")
                    if CUR_SECTION_HDR.sh_type != SectionHeader.SHTYPE_PROGDAT: raise Exception("Cannot write to non-PROGDAT section.")
                    for op in line["ops"]:
                        if op["rtype"]: raise Exception("Registers are not allowed in .string")
                        if op["ismem"]: raise Exception("Memory indexing is not allowed in .string")
                        value = evalimm(op["ival"])
                        if value["type"] != "abs": raise Exception(".string arguments must be defined.")
                        if not (-0x8000 <= value["val"] < 0x8000): raise Exception(".string arguments must be 16-bit.")
                        CUR_SECTION.words.append(value["val"])
                        _sp.s_value = CUR_SECTION.getSize()
                        _ip.s_value = _sp.s_value + CUR_SECTION_HDR.sh_addr
                    CUR_SECTION.words.append(0)
                elif cmd == ".dec":
                    if not CUR_SECTION: raise Exception("Section must be defined when writing data.")
                    if CUR_SECTION_HDR.sh_type != SectionHeader.SHTYPE_PROGDAT: raise Exception("Cannot write to non-PROGDAT section.")
                    for op in line["ops"]:
                        if op["rtype"]: raise Exception("Registers are not allowed in .dec")
                        if op["ismem"]: raise Exception("Memory indexing is not allowed in .dec")
                        value = evalimm(op["ival"])
                        if value["type"] != "abs": raise Exception(".dec arguments must be defined.")
                        if not (-0x8000 <= value["val"] < 0x8000): raise Exception(".dec arguments must be 16-bit.")
                        CUR_SECTION.words.append(value["val"])
                        _sp.s_value = CUR_SECTION.getSize()
                        _ip.s_value = _sp.s_value + CUR_SECTION_HDR.sh_addr
                elif cmd == ".deca":
                    if not CUR_SECTION: raise Exception("Section must be defined when writing data.")
                    if CUR_SECTION_HDR.sh_type != SectionHeader.SHTYPE_PROGDAT: raise Exception("Cannot write to non-PROGDAT section.")
                    for op in line["ops"]:
                        if op["rtype"]: raise Exception("Registers are not allowed in .deca")
                        if op["ismem"]: raise Exception("Memory indexing is not allowed in .deca")
                        value = evalimm(op["ival"])
                        if value["type"] == "abs":
                            CUR_SECTION.words.extend([value["val"] & 0xFFFF, (value["val"] >> 16) & 0xFFFF])
                        elif value["type"] == "lbl":
                            reloc = defRel(value["val"], _sp.s_value)
                            symbol = SYMTAB.getSymbolByID(reloc.r_symndx)
                            CUR_SECTION.words.extend([symbol.s_value & 0xFFFF, (symbol.s_value >> 16) & 0xFFFF])
                        elif value["type"] == "op":
                            MEXPR_RELOCS.append({"offset": _sp.s_value, "line": line["ln"], "shndx": file.getIDBySection(CUR_SECTION), "mexpr":value})
                            CUR_SECTION.words.extend([0, 0])
                        _sp.s_value = CUR_SECTION.getSize()
                        _ip.s_value = _sp.s_value + CUR_SECTION_HDR.sh_addr
                elif cmd == ".pad":
                    if not CUR_SECTION: raise Exception("Section must be defined when writing data.")
                    if CUR_SECTION_HDR.sh_type != SectionHeader.SHTYPE_PROGDAT: raise Exception("Cannot write to non-PROGDAT section.")
                    if len(line["ops"]) != 2: raise Exception(".pad expected 2 arguments, got "+str(len(line["ops"]))+".")
                    rep = line["ops"][0]
                    value = line["ops"][1]
                    if rep["rtype"]: raise Exception(".pad 1st argument cannot be a register.")
                    if rep["ismem"]: raise Exception(".pad 1st argument cannot be a memory reference.")
                    if value["rtype"]: raise Exception(".pad 2nd argument cannot be a register.")
                    if value["ismem"]: raise Exception(".pad 2nd argument cannot be a memmory reference.")
                    rep = evalimm(rep["ival"])
                    value = evalimm(value["ival"])
                    if rep["type"] != "abs": raise Exception(".pad 1st argument must be defined.")
                    if rep["val"] < 0: raise Exception(".pad 1st argument must be a positive integer")
                    if value["type"] != "abs": raise Exception(".pad 2nd argument must be defined.")
                    if not (-0x8000 <= value["val"] < 0x8000): raise Exception(".pad 2nd argument must be 16-bit.")
                    for i in range(rep["val"]):
                        CUR_SECTION.words.append(value["val"])
                        _sp.s_value = CUR_SECTION.getSize()
                        _ip.s_value = _sp.s_value + CUR_SECTION_HDR.sh_addr
                elif cmd == ".pada":
                    if not CUR_SECTION: raise Exception("Section must be defined when writing data.")
                    if CUR_SECTION_HDR.sh_type != SectionHeader.SHTYPE_PROGDAT: raise Exception("Cannot write to non-PROGDAT section.")
                    if len(line["ops"]) != 2: raise Exception(".pada expected 2 arguments, got "+str(len(line["ops"]))+".")
                    rep = line["ops"][0]
                    value = line["ops"][1]
                    if rep["rtype"]: raise Exception(".pada 1st argument cannot be a register.")
                    if rep["ismem"]: raise Exception(".pada 1st argument cannot be a memory reference.")
                    if value["rtype"]: raise Exception(".pada 2nd argument cannot be a register.")
                    if value["ismem"]: raise Exception(".pada 2nd argument cannot be a memmory reference.")
                    rep = evalimm(rep["ival"])
                    value = evalimm(value["ival"])
                    if rep["type"] != "abs": raise Exception(".pad 1st argument must be defined.")
                    if rep["val"] < 0: raise Exception(".pad 1st argument must be a positive integer")
                    for i in range(rep["val"]):
                        if value["type"] == "abs":
                            CUR_SECTION.words.extend([value["val"] & 0xFFFF, (value["val"] >> 16) & 0xFFFF])
                        elif value["type"] == "lbl":
                            symbol = SYMTAB.getSymbolByID(HASHTAB.getSymbolIDByString(value["val"]))
                            if symbol.s_shndx != Symbol.SDEF_ABS:
                                reloc = defRel(value["val"], _sp.s_value)
                            CUR_SECTION.words.extend([symbol.s_value & 0xFFFF, (symbol.s_value >> 16) & 0xFFFF])
                        elif value["type"] == "op":
                            MEXPR_RELOCS.append({"offset": _sp.s_value, "line": line["ln"], "shndx": file.getIDBySection(CUR_SECTION), "mexpr":value})
                            CUR_SECTION.words.extend([0, 0])
                        _sp.s_value = CUR_SECTION.getSize()
                        _ip.s_value = _sp.s_value + CUR_SECTION_HDR.sh_addr
                elif cmd == ".res":
                    if not CUR_SECTION: raise Exception("Section must be defined when declaring data.")
                    if CUR_SECTION_HDR.sh_type != SectionHeader.SHTYPE_NOBITS: raise Exception(".res can only be used in NOBITS sections.")
                    if len(line["ops"]) != 1: raise Exception(".res expected 1 argument, got "+str(len(line["ops"]))+".")
                    rep = line["ops"][0]
                    if rep["rtype"]: raise Exception(".res 1st argument cannot be a register.")
                    if rep["ismem"]: raise Exception(".res 1st argument cannot be a memory reference.")
                    rep = evalimm(rep["ival"])
                    if rep["type"] != "abs": raise Exception(".res 1st argument must be defined.")
                    if rep["val"] < 0: raise Exception(".res 1st argument must be a positive integer")
                    for i in range(rep["val"]):
                        CUR_SECTION.words.append(0)
                        _sp.s_value = CUR_SECTION.getSize()
                        _ip.s_value = _sp.s_value + CUR_SECTION_HDR.sh_addr
                elif cmd == ".resa":
                    if not CUR_SECTION: raise Exception("Section must be defined when declaring data.")
                    if CUR_SECTION_HDR.sh_type != SectionHeader.SHTYPE_NOBITS: raise Exception(".resa can only be used in NOBITS sections.")
                    if len(line["ops"]) != 1: raise Exception(".resa expected 1 argument, got "+str(len(line["ops"]))+".")
                    rep = line["ops"][0]
                    if rep["rtype"]: raise Exception(".resa 1st argument cannot be a register.")
                    if rep["ismem"]: raise Exception(".resa 1st argument cannot be a memory reference.")
                    rep = evalimm(rep["ival"])
                    if rep["type"] != "abs": raise Exception(".resa 1st argument must be defined.")
                    if rep["val"] < 0: raise Exception(".resa 1st argument must be a positive integer")
                    for i in range(rep["val"]):
                        CUR_SECTION.words.extend([0, 0])
                        _sp.s_value = CUR_SECTION.getSize()
                        _ip.s_value = _sp.s_value + CUR_SECTION_HDR.sh_addr
                elif cmd == ".org":
                    if not CUR_SECTION: raise Exception("Section must be defined to set its origin.")
                    if CUR_SECTION.getSize() != 0: raise Exception(".org can only be used at the beginning of a section.")
                    if len(line["ops"]) != 1: raise Exception(".org expected 1 argument, got "+str(len(line["ops"]))+".")
                    addr = line["ops"][0]
                    if addr["rtype"]: raise Exception(".org 1st argument cannot be a register.")
                    if addr["ismem"]: raise Exception(".org 1st argument cannot be a memory reference.")
                    addr = evalimm(addr["ival"])
                    if addr["type"] != "abs": raise Exception(".org 1st argument must be defined.")
                    if addr["val"] < _ip.s_value: raise Exception(".org cannot be used to recede backwards. (@ip="+str(_ip.s_value)+", addr="+str(rep["val"])+").")
                    _ip.s_value = addr["val"]
                    _sp.s_value = _ip.s_value
                    CUR_SECTION_HDR.sh_addr = _ip.s_value
                elif cmd == ".align":
                    if not CUR_SECTION: raise Exception("Section must be defined when defining data.")
                    if len(line["ops"]) != 2: raise Exception(".align expected 2 arguments, got "+str(len(line["ops"]))+".")
                    boundary = line["ops"][0]
                    value = line["ops"][0]
                    if boundary["rtype"]: raise Exception(".align 1st argument cannot be a register.")
                    if boundary["ismem"]: raise Exception(".align 1st argument cannot be a memory reference.")
                    if value["rtype"]: raise Exception(".align 2nd argument cannot be a register.")
                    if value["ismem"]: raise Exception(".align 2nd argument cannot be a memmory reference.")
                    boundary = evalimm(boundary["ival"])
                    value = evalimm(value["ival"])
                    if rep["type"] != "abs": raise Exception(".align 1st argument must be defined.")
                    if rep["val"] < 0: raise Exception(".align 1st argument must be a positive integer")
                    if value["type"] != "abs": raise Exception(".align 2nd argument must be defined.")
                    if not (-0x8000 <= value["val"] < 0x8000): raise Exception(".align 2nd argument must be 16-bit.")
                    rep = 2**boundary*math.ceil(_ip.s_value/2**boundary) - _ip.s_value
                    CUR_SECTION.words.extend([0]*rep)
                    _ip.s_value += rep
                elif cmd == ".section":
                    if len(line["ops"]) != 2: raise Exception(".section expected 2 arguments, got "+str(len(line["ops"]))+".")
                    name = line["ops"][0]
                    value = line["ops"][1]
                    if name["rtype"]: raise Exception(".section 1st argument cannot be a register.")
                    if name["ismem"]: raise Exception(".section 1st argument cannot be a memory reference.")
                    if name["itype"] != "lbl": raise Exception(".section 1st argument must be a label.")
                    if name["ival"].startswith("@"): raise Exception("@ symbol is reserved for assembler-defined sections.")
                    if SHSTRTAB.containsString(name["ival"]): raise Exception("Section \""+name["ival"]+"\" already exists.")
                    if value["rtype"]: raise Exception(".section 2nd argument cannot be a register.")
                    if value["ismem"]: raise Exception(".section 2nd argument cannot be a memmory reference.")
                    value = evalimm(value["ival"])
                    if value["type"] != "abs": raise Exception(".section 2nd argument must be defined.")
                    isImaged = value["val"] & 1 != 0
                    isAlloc = value["val"] & 2 != 0
                    CUR_SECTION_HDR = SectionHeader(SHSTRTAB.getIDByString(name["ival"]),
                                           SectionHeader.SHTYPE_PROGDAT if isImaged else SectionHeader.SHTYPE_NOBITS,
                                           _ip.s_value if isAlloc else 0,
                                           -1, -1, 0,
                                           0xEF00 if isImaged else 0,
                                           0, 0)
                    CUR_SECTION = GeneralSection()
                    file.addSection(CUR_SECTION_HDR, CUR_SECTION)
                    REL_SECTION_HDR = None
                    REL_SECTION = None
                    _sp.s_value = _ip.s_value
                elif cmd == ".text":
                    if len(line["ops"]) != 0: raise Exception(".text expected 0 arguments, got "+str(len(line["ops"]))+".")
                    if SHSTRTAB.containsString("text"): raise Exception("text section already exists.")
                    CUR_SECTION_HDR = SectionHeader(SHSTRTAB.getIDByString("text"), SectionHeader.SHTYPE_PROGDAT, _ip.s_value, -1, -1, 0, 0xEF00, 0, 0)
                    CUR_SECTION = GeneralSection()
                    file.addSection(CUR_SECTION_HDR, CUR_SECTION)
                    REL_SECTION_HDR = None
                    REL_SECTION = None
                    _sp.s_value = _ip.s_value
                elif cmd == ".data":
                    if len(line["ops"]) != 0: raise Exception(".data expected 0 arguments, got "+str(len(line["ops"]))+".")
                    if SHSTRTAB.containsString("data"): raise Exception("data section already exists.")
                    CUR_SECTION_HDR = SectionHeader(SHSTRTAB.getIDByString("data"), SectionHeader.SHTYPE_PROGDAT, _ip.s_value, -1, -1, 0, 0x0000, 0, 0)
                    CUR_SECTION = GeneralSection()
                    file.addSection(CUR_SECTION_HDR, CUR_SECTION)
                    REL_SECTION_HDR = None
                    REL_SECTION = None
                    _sp.s_value = _ip.s_value
                elif cmd == ".bss":
                    if len(line["ops"]) != 0: raise Exception(".bss expected 0 arguments, got "+str(len(line["ops"]))+".")
                    if SHSTRTAB.containsString("bss"): raise Exception("bss section already exists.")
                    CUR_SECTION_HDR = SectionHeader(SHSTRTAB.getIDByString("bss"), SectionHeader.SHTYPE_NOBITS, _ip.s_value, -1, -1, 0, 0xEF00, 0, 0)
                    CUR_SECTION = GeneralSection()
                    file.addSection(CUR_SECTION_HDR, CUR_SECTION)
                    REL_SECTION_HDR = None
                    REL_SECTION = None
                    _sp.s_value = _ip.s_value
                else:
                    if not CUR_SECTION: raise Exception("Section must be defined when writing data.")
                    if CUR_SECTION_HDR.sh_type != SectionHeader.SHTYPE_PROGDAT: raise Exception("Cannot write to non-PROGDAT section.")
                    ret, relocs = matchInst(cmd, line["ops"])
                    for reloc in relocs:
                        if line["ops"][reloc["opN"]]["itype"] == "mexpr":
                            MEXPR_RELOCS.append({"offset": _ip.s_value - _sp.s_value + reloc["offset"],
                                                 "line": line["ln"],
                                                 "shndx": file.getIDBySection(CUR_SECTION),
                                                 "mexpr": line["ops"][reloc["opN"]]["ival"]})
                        elif line["ops"][reloc["opN"]]["itype"] == "lbl":
                            relobj = defRel(line["ops"][reloc["opN"]]["ival"], _ip.s_value - _sp.s_value + reloc["offset"])
                            symbol = SYMTAB.getSymbolByID(relobj.r_symndx)
                            ret[reloc["offset"]] = symbol.s_value & 0xFFFF
                            ret[reloc["offset"]+1] = (symbol.s_value >> 16) >> 0xFFFF
                    CUR_SECTION.words.extend(ret)
                    _ip.s_value += len(ret)
        except Exception as e:
            print("$ - (ERROR) " + str(line["ln"]) + " - " + str(e))
            exit(-1)
    
    try:
        if verbose: print("$ - Verifying symbols")
        for symbol in SYMTAB.symbols:
            if symbol.s_shndx == Symbol.SDEF_UNDEF and symbol.s_info != Symbol.SINFO_EXTERN:
                raise Exception("Non-extern symbol \""+SYMSTRTAB.getStringByID(symbol.s_name)+"\" is undefined.")  
        if verbose:
            print("$ - Symbols verified")
            print("$ - Resolving math expressions")
        for mexprrel in MEXPR_RELOCS:
            val = evalimm(mexprrel["mexpr"])
            if val["type"] != "abs": raise Exception(str(mexprrel["line"]) + " - Math expression \""+reprMath(val)+"\" couldn't be evaluated to an absolute value.")
            _, section = file.getSection(mexprrel["shndx"])
            section.words[mexprrel["offset"]] = val["val"] & 0xFFFF
            section.words[mexprrel["offset"]+1] = (val["val"] >> 16) & 0xFFFF
        if verbose:
            print("$ - "+str(len(MEXPR_RELOCS))+" math expressions solved")
            print("$ - Translation complete")
    except Exception as e:
        print("$ - (ERROR) " + str(e))
        exit(-1)

    out_filepath = os.path.splitext(os.path.basename(in_filepath))[0] + outext
    out_filepath = os.path.join(out_dirpath, out_filepath)
    with open(out_filepath, "wb") as f:
        f.write(SLBFManager.serializeBytes(file))
    print("$ - (SUCCESS) "+in_filepath+" -> "+out_filepath)

def main(argv):
    opts, args = getopt.getopt(argv, "d:hv", ["help", "verbose"])
    files = []
    global verbose, outdir
    
    for o, a in opts:
        if o in ["-h", "--help"]:
            print("Assembles Mercury Assembly files into SLBF object files.")
            print("Usage: py asm.py [options] files...")
            print("Options:")
            print("\t-h | --help: Display this message.")
            print("\t-v | --verbose: Display extra information on the assembling process.")
            print("\t-d OUTPUT: Specify OUTPUT as the output directory. Creates OUTPUT if it does not exist. Must not be a file.\n")
            print("\tfile... is a list of assembly files to compile.\n")
            exit(0)
        if o in ["-v", "--verbose"]:
            verbose = True
        if o == "-d":
            if os.path.isfile(a):
                print("[WARNING] Specified output directory \""+a+"\" is already an existing file.")
                continue
            outdir = a
    if not outdir:
        print("[WARNING] Valid output directory was not specified. Defaulting to current directory")
        outdir = "."
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    for arg in args:
        if not os.path.isfile(arg):
            print("[WARNING] \""+arg+"\" is not a file or does not exist.")
            continue
        files.append(arg)
    if len(files) == 0:
        print("[FATAL] No files to assemble.")
        exit(-1)
    
    for in_filepath in files:
        try:
            assemble(in_filepath, outdir)
        except Exception as e:
            print("[FATAL]", os.path.basename(in_filepath)+":"+e.args[0].split("\n")[0])
            

if __name__ == "__main__":
    main(sys.argv[1:])
import os, sys, getopt, math

from SLBFManager import *

verbose = False
entrysymbol = "main"

def link(is_build=False, in_filepaths=[]):
    if verbose: print("$ - Begin Linker")
    ofile = SLBFManager.newFile(SLBFHeader.HTYPE_OBJ if is_build else SLBFHeader.HTYPE_EXE)

    SHSTRTAB_HDR, SHSTRTAB = ofile.getSection(ofile.header.h_shstrndx)
    HASHTAB_HDR, HASHTAB = ofile.getSection(ofile.header.h_hashtabndx)
    SYMTAB_HDR, SYMTAB = ofile.getSection(ofile.header.h_symtabndx)
    SYMSTRTAB_HDR, SYMSTRTAB = ofile.getSection(SYMTAB_HDR.sh_link)
    
    externrelocs = {} # Maps a name (global symbol) to a list of relocation data
    # This data is as such :
    # {
    #    "section": Id of relocation section in build file
    #    "relid": Id of relocation in the relocation section
    # }
    # References can then be evaluated after assembling the entire file.

    for in_filepath in in_filepaths:
        with open(in_filepath, "rb") as f:
            in_file = SLBFManager.deserializeBytes(f.read())
            f.close()
        I_SHSTRTAB_HDR, I_SHSTRTAB = in_file.getSection(in_file.header.h_shstrndx)
        I_HASHTAB_HDR, I_HASHTAB = in_file.getSection(in_file.header.h_hashtabndx)
        I_SYMTAB_HDR, I_SYMTAB = in_file.getSection(in_file.header.h_symtabndx)
        I_SYMSTRTAB_HDR, I_SYMSTRTAB = in_file.getSection(I_SYMTAB_HDR.sh_link)
        
        if verbose: print("[FILE] " + in_filepath)
                
        def correctSectionAddress(new_sectionhdr, new_section):
            didCorrect = False
            for i in range(ofile.header.h_shnum):
                SECTION_HEADER, SECTION = ofile.getSection(i)
                if SECTION_HEADER.sh_type not in [SectionHeader.SHTYPE_PROGDAT, SectionHeader.SHTYPE_NOBITS]: continue
                
                if (new_sectionhdr.sh_addr < SECTION_HEADER.sh_size + SECTION_HEADER.sh_addr) and (new_sectionhdr.sh_addr + new_sectionhdr.sh_size > SECTION_HEADER.sh_addr):
                    # If the new section overlaps with a previous section, relocate.
                    didCorrect = True
                    offset = SECTION_HEADER.sh_addr + SECTION_HEADER.sh_size - new_sectionhdr.sh_addr
                    new_sectionhdr.sh_addr += offset
                    if new_sectionhdr.sh_addr + new_sectionhdr.sh_size >= 0xFFFFFFFF: raise Exception("Section \""+SHSTRTAB.getStringByID(new_sectionhdr.sh_name)+"\" from \""+in_filepath+"\" has exceeded address space width.")

            if didCorrect: return offset + correctSectionAddress(new_sectionhdr, new_section) # Repeat correction until a spot is found or we run out of address space
            return 0
        
        if verbose: print("$ - Resolve absolute symbols")
        running_total = 0
        for symid in range(len(I_SYMTAB.symbols)): # Take care of all the absolute symbols
            symbol = I_SYMTAB.symbols[symid]
            symname = I_SYMSTRTAB.getStringByID(symbol.s_name)
            if symbol.s_shndx != 0xFFFF: continue
            new_symbol = Symbol(SYMSTRTAB.getIDByString(symname), symbol.s_value, symbol.s_info, Symbol.SDEF_ABS)
            if HASHTAB.containsName(ofile, symname):
                if symbol.s_info == Symbol.SINFO_GLOBAL: # Global symbols must be completely unique.
                    raise Exception("Global or weak symbol \""+symname+"\" is already defined.")
                elif symbol.s_info == Symbol.SINFO_WEAK: # Ignore later weak symbols.
                    if verbose: print("\t\t"+symname+"\t- Reset to from weak to local because of a previously defined global/weak symbol.")
                    symbol.s_info = Symbol.SINFO_LOCAL
                    new_symbol.s_info = Symbol.SINFO_LOCAL
            if symbol.s_info == Symbol.SINFO_LOCAL: # Local absolute values aren't needed in other files, so we can remove them.
                newid = 0
            else: # Otherwise, we can add them to the symbol table.
                newid = SYMTAB.addSymbol(ofile, new_symbol, symbol.s_info in [Symbol.SINFO_GLOBAL, Symbol.SINFO_WEAK]) # Add with name if global or weak
            
            total = 0
            for i in range(in_file.header.h_shnum):
                I_RELSEC_HDR, I_RELSEC = in_file.getSection(i)
                if I_RELSEC_HDR.sh_type != SectionHeader.SHTYPE_RELTAB: continue
                ri = 0
                while True:
                    if ri >= len(I_RELSEC.relocs): break
                    reloc = I_RELSEC.relocs[ri]
                    if reloc.r_symndx != symid:
                        ri+=1
                        continue
                    if newid == 0: # We need to remove relocations to this absolute value if it's local.
                        del I_RELSEC.relocs[ri]
                        continue
                    reloc.tempndx = newid # Store the new ID
                    total += 1
                    ri += 1
            if verbose and total > 0: print("\t"+symname+" -\t"+str(total)+" patches.")
            running_total += total
        if verbose: print("$ - Resolved "+str(running_total)+" absolute symbols")
        
        for i in range(in_file.header.h_shnum):
            SECTION_HEADER, SECTION = in_file.getSection(i)
            if SECTION_HEADER.sh_type not in [SectionHeader.SHTYPE_PROGDAT, SectionHeader.SHTYPE_NOBITS]: continue
            sectionname = I_SHSTRTAB.getStringByID(SECTION_HEADER.sh_name)
            N_SECTION_HEADER = SectionHeader(SHSTRTAB.getIDByString(sectionname),
                                            SECTION_HEADER.sh_type, SECTION_HEADER.sh_addr,
                                            -1, SECTION_HEADER.sh_size, 0,
                                            SECTION_HEADER.sh_alval, SECTION_HEADER.sh_align, SECTION_HEADER.sh_entsize)
            N_SECTION = GeneralSection(SECTION.words)
            if SECTION_HEADER.sh_type == SectionHeader.SHTYPE_NOBITS:
                N_SECTION.words.extend([0]*SECTION_HEADER.sh_size)
            if verbose: print("[SECTION]", sectionname)
            
            offset = correctSectionAddress(N_SECTION_HEADER, N_SECTION)
            if verbose and offset > 0: print("\t-: Section relocated +"+str(offset)+" W")
            
            N_SECTION_ID = ofile.addSection(N_SECTION_HEADER, N_SECTION)
            
            for j in range(in_file.header.h_shnum): # Fetch the relocation table if it exists
                I_RELSEC_HDR, I_RELSEC = in_file.getSection(j)
                if I_RELSEC_HDR.sh_type != SectionHeader.SHTYPE_RELTAB or I_RELSEC_HDR.sh_link != i: continue
                RELSEC_HDR = SectionHeader(SHSTRTAB.getIDByString(I_SHSTRTAB.getStringByID(I_RELSEC_HDR.sh_name)),
                                        SectionHeader.SHTYPE_RELTAB, 0,
                                        -1, -1, N_SECTION_ID,
                                        I_RELSEC_HDR.sh_alval, I_RELSEC_HDR.sh_align, I_RELSEC_HDR.sh_entsize)
                RELSEC = RelocTable()
                RELSEC_ID = ofile.addSection(RELSEC_HDR, RELSEC)
                if verbose: print("\t-: Found relocation data")
                break
            else:
                I_RELSEC_HDR, I_RELSEC = None, None
                RELSEC = None
                RELSEC_ID = 0
                if verbose: print("\t-: No relocation data")          
            
            if verbose: print("\t$: Resolve section symbols")
            running_total = 0
            for symid in range(len(I_SYMTAB.symbols)): # Deal with symbols in this section
                symbol = I_SYMTAB.symbols[symid]
                symname = I_SYMSTRTAB.getStringByID(symbol.s_name)
                
                total = 0
                if symbol.s_shndx == i: # Fix up all symbols in this section
                    new_symbol = Symbol(SYMSTRTAB.getIDByString(symname), symbol.s_value, symbol.s_info, N_SECTION_ID)
                    new_symbol.s_value += offset # Fix the addressing

                    if HASHTAB.containsName(ofile, symname):
                        if symbol.s_info == Symbol.SINFO_GLOBAL: # Global symbols must be completely unique.
                            raise Exception("Global or weak symbol \""+symname+"\" is already defined.")
                        elif symbol.s_info == Symbol.SINFO_WEAK: # Ignore later weak symbols.
                            if verbose: print("\t\t"+symname+"\t- Reset to from weak to local because of a previously defined global/weak symbol.")
                            symbol.s_info = Symbol.SINFO_LOCAL
                            new_symbol.s_info = Symbol.SINFO_LOCAL
                    newid = SYMTAB.addSymbol(ofile, new_symbol, symbol.s_info in [Symbol.SINFO_GLOBAL, Symbol.SINFO_WEAK]) # Add with name if global or weak
                    
                    for j in range(in_file.header.h_shnum):
                        I_RELSEC_HDR2, I_RELSEC2 = in_file.getSection(j)
                        if I_RELSEC_HDR2.sh_type != SectionHeader.SHTYPE_RELTAB: continue
                        for reloc in I_RELSEC2.relocs:
                            if reloc.r_symndx != symid: continue
                            reloc.tempndx = newid
                            total += 1 
                    if verbose and total > 0: print("\t\t"+symname+"\t- "+str(total)+" patch(es).")
                elif symbol.s_info == Symbol.SINFO_EXTERN and RELSEC_ID != 0: # Handle external symbols for this section's reloc table if it exists
                    for reloc in I_RELSEC.relocs:
                        if reloc.r_symndx != symid: continue
                        relocref = externrelocs.get(symname, None)
                        if not relocref: relocref = [] # Just in case we get some weird bugs by using the same list in .get()
                        relocref.append({
                            "section": RELSEC_ID, # Keeps track of the section in the BUILD file that'll contain this relocation to patch
                            "relid": len(RELSEC.relocs) # ID of the relocation in the BUILD file's relocation table
                        })
                        RELSEC.relocs.append(reloc)
                        externrelocs[symname] = relocref
                        total += 1
                    if verbose and total > 0: print("\t\t(EXTERN) "+symname+"\t- "+str(total)+" relocation(s) added.")
                else:
                    continue
                running_total += total
            if verbose: print("\t-: Resolved "+str(running_total)+" section symbols")
            
            if RELSEC:
                if verbose: print("\t$: Fix non-external relocations")
                total = 0
                for reloc in I_RELSEC.relocs:
                    reloc.r_symndx = reloc.tempndx
                    if reloc.tempndx != 0: # If it's not external, add it to the new relocs section
                        RELSEC.relocs.append(reloc)
                        total += 1
                if verbose: print("\t-:", total, "non-external relocations added")
        
        print("$ - (SUCCESS) Linked "+in_filepath)
        print()
    
    if verbose: print("$ - Patch external relocations")
    total = 0
    for key in externrelocs:
        if not HASHTAB.containsName(ofile, key):
            raise Exception("Referenced global symbol \""+key+"\" has been left undefined.")
        id = HASHTAB.getSymbolIDByName(ofile, key)
        for relocdat in externrelocs.get(key, []):
            ofile.sections[relocdat["section"]].relocs[relocdat["relid"]].r_symndx = id
            total += 1
    if verbose: print("$ - Patched "+str(total)+" external relocation(s)")
    
    if verbose: print("$ - Patch relocations with new symbol values/addresses")
    total = 0
    for i in range(ofile.header.h_shnum):
        RELSEC_HDR, RELSEC= ofile.getSection(i)
        if RELSEC_HDR.sh_type != SectionHeader.SHTYPE_RELTAB: continue
        SECTION_HDR, SECTION = ofile.getSection(RELSEC_HDR.sh_link)
        for reloc in RELSEC.relocs:
            symbol = SYMTAB.symbols[reloc.r_symndx]
            SECTION.words[reloc.r_offset] = symbol.s_value & 0xFFFF
            SECTION.words[reloc.r_offset+1] = (symbol.s_value >> 16) & 0xFFFF
            total += 1
    if verbose: print("$ -", total, "relocations patched.")
    
    if not is_build: # If it's executable
        if not HASHTAB.containsName(ofile, entrysymbol.lower()):
            raise Exception("Could not find global entry symbol \""+entrysymbol.lower()+"\"")
        id = HASHTAB.getSymbolIDByName(ofile, entrysymbol.lower())
        ofile.header.h_entry = id
        if verbose: print("$ - Set entry symbol to \""+entrysymbol.lower()+"\"")
    
    return ofile

def main(argv):
    opts, args = getopt.getopt(argv, "o:hv", ["help", "lib", "verbose", "entry="])
    files = []
    islib = False
    outfile = "a.mx"
    global verbose, entrysymbol

    for o, a in opts:
        if o in ["-h", "--help"]:
            print("Links Mercury SLBF Object files into executable files.")
            print("Usage: py lexer.py [options] files...")
            print("Options:")
            print("\t-h | --help: Display this message.")
            print("\t-v | --verbose: Display extra information on the linking process.")
            print("\t--lib: Builds a library out of the specified files instead of an executable.")
            print("\t--entry: Specifies an entry symbol for executables (Default: main)")
            print("\t-o OUTPUT: Specify OUTPUT as the output file.\n")
            print("\tfile... is a list of object files to link.\n")
            exit(0)
        if o in ["-v", "--verbose"]:
            verbose = True
        if o == "--lib":
            if outfile == "a.mx": outfile = "a.mlib"
            islib = True
        if o == "--entry":
            entrysymbol = a
        if o == "-o":
            if os.path.isfile(a):
                print("[WARNING] Output file already exists and will be overwritten.")
                if input("Continue linking? (Y/N)").lower() != "y": exit(0)
            outfile = a
    for arg in args:
        if not os.path.isfile(arg):
            print("[WARNING] \""+arg+"\" is not a file or does not exist.")
            continue
        files.append(arg)
    if len(files) == 0:
        print("[FATAL] No files to link.")
        exit(-1)
        
    try:
        efile = link(islib, files)
    except Exception as e:
        print("[FATAL] Couldn't link due to the following exception:")
        print(e)
        exit(-1)
    
    with open(outfile, "wb") as f:
        f.write(SLBFManager.serializeBytes(efile))
    print("$ - (SUCCESS) Linked to "+outfile)

if __name__ == "__main__":
    main(sys.argv[1:])
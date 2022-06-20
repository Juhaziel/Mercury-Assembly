import os, sys, getopt

from SLBFManager import *

verbose = False

def load(in_filepath):
    if verbose: print("$ - Begin Flat Loader")
    with open(in_filepath, "rb") as f:
        in_file = SLBFManager.deserializeBytes(f.read())
        f.close()
    
    if in_file.header.h_type != 2: # If this is not an executable
        raise Exception("Sepecified input file is not an executable file.")
    
    lines = []
    
    SHSTRTAB_HDR, SHSTRTAB = in_file.getSection(in_file.header.h_shstrndx)
    
    for i in range(in_file.header.h_shnum):
        hdr, section = in_file.getSection(i)
        if hdr.sh_type == 1: # If this section is PROGDAT
            if verbose: print("\t{:08X} - {}".format(hdr.sh_addr, repr(SHSTRTAB.getStringByID(hdr.sh_name))))
            curline = {"addr": hdr.sh_addr, "words": []}
            for j in range(hdr.sh_size):
                curline["words"].append(f"{section.words[j]:04x}")
            lines.append(curline)
    
    def sortkey(line):
        return line["addr"]
    
    lines.sort(key=sortkey)
    
    for i in range(len(lines)):
        lines[i] = f"{lines[i]['addr']:08x}: {' '.join(lines[i]['words'])}"
        
    return lines
        
    

def main(argv):
    opts, args = getopt.getopt(argv, "o:hv", ["help", "verbose"])
    outfile = "a.lsi"
    global verbose
    
    for o, a in opts:
        if o in ["-h", "--help"]:
            print("Creates a logisim memory image from a Mercury SLBF executable with no section relocation.")
            print("Usage: py flatloder.py [options] file")
            print("Options:")
            print("\t-h | --help: Display this message.")
            print("\t-v | --verbose: Display extra information on the loading process.")
            print("\t-o OUTPUT: Specify OUTPUT as the output file.\n")
            print("\tfile is the executable file to load.\n")
            exit(0)
        if o in ["-v", "--verbose"]:
            verbose = True
        if o == "-o":
            if os.path.isfile(a):
                print("[WARNING] Output file already exists and will be overwritten.")
                if input("Continue linking? (Y/N)").lower() != "y": exit(0)
            outfile = a
    
    if len(args) == 0:
        print("[FATAL] No executable file was specified.")
        exit(-1)
        
    if len(args) > 1:
        print("[WARNING] There is more than one input file specified.\nOnly the first one will be used.")
    
    if not os.path.isfile(args[0]):
        print("[FATAL] \""+args[0]+"\" is not a file or does not exist.")
        exit(-2)
    
    try:
        mtextdumplines = load(args[0])
    except Exception as e:
        print("[FATAL] Couldn't flat load due to the following exception:")
        print(e)
        exit(-3)
        
    with open(outfile, "w") as f:
        f.write("v3.0 hex words addressed\n")
        for line in mtextdumplines:
            f.write(str(line) + "\n")
    
    print("$ - (SUCCESS) Loaded flat to "+outfile)
        

if __name__ == "__main__":
    main(sys.argv[1:])
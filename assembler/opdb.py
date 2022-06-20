import re

db = [
    ["rst", [], 0x0000, []],
    ["ret", [], 0x2000, []],
    ["rti|reti", [], 0x3000, []],
    ["j(\\w{1,2})", ["addr0"], 0x0800, ["rcc", "aD0"]],
    ["j(\\w{1,2})", ["addr16"], 0x0A00, ["rcc", "aD0", "iw0"]],
    ["j(\\w{1,2})", ["addr32"], 0x0C00, ["rcc", "aD0", "id0"]],
    ["call", ["addr0"], 0x2800, ["aD0"]],
    ["call", ["addr16"], 0x2A00, ["aD0", "iw0"]],
    ["call", ["addr32"], 0x2C00, ["aD0", "id0"]],
    ["int", ["imm16"], 0x3E00, ["iw0"]],
    ["int", ["reg16"], 0x3F00, "rS0"],
    ["add", ["reg16", "imm16"], 0x4000, ["rD0", "iw1"]],
    ["add", ["reg16", "reg16"], 0x4100, ["rD0", "rS1"]],
    ["sub", ["reg16", "imm16"], 0x5000, ["rD0", "iw1"]],
    ["sub", ["reg16", "reg16"], 0x5100, ["rD0", "rS1"]],
    ["adc", ["reg16", "imm16"], 0x4200, ["rD0", "iw1"]],
    ["adc", ["reg16", "reg16"], 0x4300, ["rD0", "rS1"]],
    ["sbc", ["reg16", "imm16"], 0x5200, ["rD0", "iw1"]],
    ["sbc", ["reg16", "reg16"], 0x5300, ["rD0", "rS1"]],
    ["cmp", ["reg16", "imm16"], 0x5400, ["rD0", "iw1"]],
    ["cmp", ["reg16", "reg16"], 0x5500, ["rD0", "rS1"]],
    ["inc", ["reg16"], 0x4700, ["rD0"]],
    ["dec", ["reg16"], 0x5700, ["rD0"]],
    ["and", ["reg16", "imm16"], 0x4800, ["rD0", "iw1"]],
    ["and", ["reg16", "reg16"], 0x4900, ["rD0", "rS1"]],
    ["nand", ["reg16", "imm16"], 0x5800, ["rD0", "wi1"]],
    ["nand", ["reg16", "reg16"], 0x5900, ["rD0", "rS1"]],
    ["or", ["reg16", "imm16"], 0x4A00, ["rD0", "iw1"]],
    ["or", ["reg16", "reg16"], 0x4B00, ["rD0", "rS1"]],
    ["nor", ["reg16", "imm16"], 0x5A00, ["rD0", "iw1"]],
    ["nor", ["reg16", "reg16"], 0x5B00, ["rD0", "rS1"]],
    ["xor", ["reg16", "imm16"], 0x4C00, ["rD0", "iw1"]],
    ["xor", ["reg16", "reg16"], 0x4D00, ["rD0", "rS1"]],
    ["xnor", ["reg16", "imm16"], 0x5C00, ["rD0", "iw1"]],
    ["xnor", ["reg16", "reg16"], 0x5D00, ["rD0", "rS1"]],
    ["not", ["reg16"], 0x5F00, ["rD0"]],
    ["lsl", ["reg16"], 0x6900, ["rD0"]],
    ["lsr", ["reg16"], 0x7900, ["rD0"]],
    ["rol", ["reg16"], 0x6B00, ["rD0"]],
    ["ror", ["reg16"], 0x7B00, ["rD0"]],
    ["swp|swap", ["reg16"], 0x6F00, ["rD0"]],
    ["swpl|swapl", ["reg32"], 0x7F00, ["rD0"]],
    ["mov", ["mem0", "reg16"], 0x8000, ["aD0", "rS1"]],
    ["mov", ["mem16", "reg16"], 0x8200, ["aD0", "rS1", "iw0"]],
    ["mov", ["mem32", "reg16"], 0x8400, ["aD0", "rS1", "id0"]],
    ["mov", ["reg16", "reg16"], 0x8700, ["rD0", "rS1"]],
    ["mov|movl", ["mem0", "reg32"], 0x9000, ["aD0", "rS1"]],
    ["mov|movl", ["mem16", "reg32"], 0x9200, ["aD0", "rS1", "iw0"]],
    ["mov|movl", ["mem32", "reg32"], 0x9400, ["aD0", "rS1", "id0"]],
    ["mov|movl", ["reg32", "reg32"], 0x9700, ["rD0", "rS1"]],
    ["mvi|movi|mov", ["mem0", "imm16"], 0xA000, ["aD0", "iw1"]],
    ["mvi|movi|mov", ["mem16", "imm16"], 0xA200, ["aD0", "iw1", "iw0"]],
    ["mvi|movi|mov", ["mem32", "imm16"], 0xA400, ["aD0", "iw1", "id0"]],
    ["mvi|movi|mov", ["reg16", "imm16"], 0xA700, ["rD0", "iw1"]],
    ["mvi|mvil|movi|movil|mov|movl", ["mem0", "imm32"], 0xB000, ["aD0", "id1"]],
    ["mvi|mvil|movi|movil|mov|movl", ["mem16", "imm32"], 0xB200, ["aD0", "id1", "iw0"]],
    ["mvi|mvil|movi|movil|mov|movl", ["mem32", "imm32"], 0xB400, ["aD0", "id1", "id0"]],
    ["mvi|mvil|movi|movil|mov|movl", ["reg32", "imm32"], 0xB700, ["rD0", "id1"]],
    ["mvm|movm|mov", ["reg16", "mem0"], 0xC000, ["rD0", "aS1"]],
    ["mvm|movm|mov", ["reg16", "mem16"], 0xC200, ["rD0", "aS1", "iw1"]],
    ["mvm|movm|mov", ["reg16", "mem32"], 0xC400, ["rD0", "aS1", "id1"]],
    ["mvm|mvml|movm|movml|mov|movl", ["reg32", "mem0"], 0xD000, ["rD0", "aS1"]],
    ["mvm|mvml|movm|movml|mov|movl", ["reg32", "mem16"], 0xD200, ["rD0", "aS1", "iw1"]],
    ["mvm|mvml|movm|movml|mov|movl", ["reg32", "mem32"], 0xD400, ["rD0", "aS1", "id1"]],
    ["mvm|movm|mov", ["mem32", "mem32"], 0xE000, ["mvm", "id1", "id0"]],
    ["mvml|movml|movl", ["mem32", "mem32"], 0xF000, ["mvm", "id1", "id0"]],
    ["push|psh", ["reg16"], 0x8F00, ["rsp", "rS0"]],
    ["push|pushl|psh|pshl", ["reg32"], 0X9F00, ["rsp", "rS0"]],
    ["push|pushi|phi", ["imm16"], 0X8E00, ["rsp", "iw0"]],
    ["push|pushl|pushi|pushil|phi|phil", ["imm32"], 0X9E00, ["rsp", "id0"]],
    ["push|pushm|phm", ["mem0"], 0x8800, ["rsp", "aS0"]],
    ["push|pushm|phm", ["mem16"], 0x8A00, ["rsp", "aS0", "iw0"]],
    ["push|pushm|phm", ["mem32"], 0x8C00, ["rsp", "aS0", "id0"]],
    ["pushl|pushml|phml", ["mem0"], 0x9800, ["rsp", "aS0"]],
    ["pushl|pushml|phml", ["mem16"], 0x9A00, ["rsp", "aS0", "iw0"]],
    ["pushl|pushml|phml", ["mem32"], 0x9C00, ["rsp", "aS0", "id0"]],
    ["push|psh", ["reg16", "reg"], 0x8F00, ["rS0", "rD1"]],
    ["push|pushl|psh|pshl", ["reg32", "reg"], 0X9F00, ["rS0", "rD1"]],
    ["push|pushi|phi", ["imm16", "reg"], 0X8E00, ["iw0", "rD1"]],
    ["push|pushl|pushi|pushil|phi|phil", ["imm32", "reg"], 0X9E00, ["id0", "rD1"]],
    ["push|pushm|phm", ["mem0", "reg"], 0x8800, ["aS0", "rD1"]],
    ["push|pushm|phm", ["mem16", "reg"], 0x8A00, ["aS0", "rD1", "iw0"]],
    ["push|pushm|phm", ["mem32", "reg"], 0x8C00, ["aS0", "rD1", "id0"]],
    ["pushl|pushml|phml", ["mem0", "reg"], 0x9800, ["aS0", "rD1"]],
    ["pushl|pushml|phml", ["mem16", "reg"], 0x9A00, ["aS0", "rD1", "iw0"]],
    ["pushl|pushml|phml", ["mem32", "reg"], 0x9C00, ["aS0", "rD1", "id0"]],
    ["pop", ["reg16"], 0xAF00, ["rsp", "rD0"]],
    ["pop|popl", ["reg32"], 0xBF00, ["rsp", "rD0"]],
    ["pop|popm|ppm", ["mem0"], 0xA800, ["rsp", "aD0"]],
    ["pop|popm|ppm", ["mem16"], 0xAA00, ["rsp", "aD0", "iw0"]],
    ["pop|popm|ppm", ["mem32"], 0xAC00, ["rsp", "aD0", "id0"]],
    ["popl|popml|ppml", ["mem0"], 0xB800, ["rsp", "aD0"]],
    ["popl|popml|ppml", ["mem16"], 0xBA00, ["rsp", "aD0", "iw0"]],
    ["popl|popml|ppml", ["mem32"], 0xBC00, ["rsp", "aD0", "id0"]],
    ["pop", ["reg16", "reg"], 0xAF00, ["rD0", "rS1"]],
    ["pop|popl", ["reg32", "reg"], 0xBF00, ["rD0", "rS1"]],
    ["pop|popm|ppm", ["mem0", "reg"], 0xA800, ["aD0", "rS1"]],
    ["pop|popm|ppm", ["mem16", "reg"], 0xAA00, ["aD0", "rS1", "iw0"]],
    ["pop|popm|ppm", ["mem32", "reg"], 0xAC00, ["aD0", "rS1", "id0"]],
    ["popl|popml|ppml", ["mem0", "reg"], 0xB800, ["aD0", "rS1"]],
    ["popl|popml|ppml", ["mem16", "reg"], 0xBA00, ["aD0", "rS1", "iw0"]],
    ["popl|popml|ppml", ["mem32", "reg"], 0xBC00, ["aD0", "rS1", "id0"]],
    ["nop", [], 0xEF00, []],
    ["hlt|halt", [], 0xFF00, []]
]

condcodes = {
    "l|n":      0b0000,
    "ge|p":     0b0001,
    "eq|z":     0b0010,
    "ne|nz":    0b0011,
    "v":        0b0100,
    "nv":       0b0101,
    "c":        0b0110,
    "nc":       0b0111,
    "le":       0b1000,
    "g":        0b1001,
    "i":        0b1010,
    "ni":       0b1011,
    "s":        0b1100,
    "ns":       0b1101,
    "mp":       0b1110,
    "nr":       0b1111
}

# Expects immediate operands to have been converted to default values.
# itypes should be kept
# Returns a word-list object and potential relocation offsets
def matchInst(cmd, ops):
    for descriptor in db:
        nameMatch = re.match("("+descriptor[0]+")$", cmd)
        if not nameMatch: continue
        if len(descriptor[1]) != len(ops): continue
        for i in range(len(ops)):
            opermatches = False
            opc = descriptor[1][i]
            if opc in ["imm", "imm16", "imm32"]:
                if ops[i]["ismem"]: break
                if ops[i]["rtype"]: break
                if not ops[i]["itype"]: break
                if opc == "imm16":
                    if ops[i]["itype"] != "abs": break
                    if not (ops[i]["ival"] & 0xFFFF < 0x10000): break
            elif opc in ["reg", "reg16", "reg32"]:
                if ops[i]["ismem"]: break
                if ops[i]["itype"]: break
                if not ops[i]["rtype"]: break
                if opc == "reg16":
                    if ops[i]["rtype"] != "r16": break
                if opc == "reg32":
                    if ops[i]["rtype"] != "r32": break
            elif opc == "addr0":
                if ops[i]["ismem"]: break
                if ops[i]["itype"]: break
                if not ops[i]["rtype"]: break
            elif opc == "addr16":
                if ops[i]["ismem"]: break
                if ops[i]["itype"] != "abs": break
                if not (ops[i]["ival"] & 0xFFFF < 0x10000): break
                if not ops[i]["rtype"]:
                    ops[i]["rtype"] = "r16"
                    ops[i]["rval"] = 0b1111 # %Z+imm16
            elif opc == "addr32":
                if ops[i]["ismem"]: break
                if not ops[i]["itype"]: break
                if not ops[i]["rtype"]:
                    ops[i]["rtype"] = "r16"
                    ops[i]["rval"] = 0b1111 # %Z+imm32
            elif opc == "mem0":
                if not ops[i]["ismem"]: break
                if ops[i]["itype"]: break
                if not ops[i]["rtype"]: break
            elif opc == "mem16":
                if not ops[i]["ismem"]: break
                if ops[i]["itype"] != "abs": break
                if not (ops[i]["ival"] & 0xFFFF < 0x10000): break
                if not ops[i]["rtype"]:
                    ops[i]["rtype"] = "r16"
                    ops[i]["rval"] = 0b1111 # %Z+imm16
            elif opc == "mem32":
                if not ops[i]["ismem"]: break
                if not ops[i]["itype"]: break
                if not ops[i]["rtype"]:
                    ops[i]["rtype"] = "r16"
                    ops[i]["rval"] = 0b1111 # %Z+imm32
        else:
            opermatches = True
        if not opermatches: continue
        relocs = []
        ret = [descriptor[2]]        
        for flag in descriptor[3]:
            if flag[0:2] == "rS":
                opN = int(flag[2:])
                ret[0] &= ~0x00F0
                ret[0] |= ops[opN]["rval"] << 4
            elif flag[0:2] == "rD":
                opN = int(flag[2:])
                ret[0] &= ~0x000F
                ret[0] |= ops[opN]["rval"]
            elif flag[0:2] == "iw":
                opN = int(flag[2:])
                ret.append(ops[opN]["ival"] & 0xFFFF)
            elif flag[0:2] == "id":
                opN = int(flag[2:])
                if ops[opN]["itype"] != "abs":
                    relocs.append({"offset": len(ret), "opN": opN})
                    ret.extend([0, 0])
                else:
                    ret.append(ops[opN]["ival"] & 0xFFFF)
                    ret.append((ops[opN]["ival"] >> 16) & 0xFFFF)
            elif flag[0:2] == "aS":
                opN = int(flag[2:])
                ret[0] &= ~0x00F0
                ret[0] |= ops[opN]["rval"] << 4
                if ops[opN]["rtype"] == "r32": ret[0] += 0x0100
            elif flag[0:2] == "aD":
                opN = int(flag[2:])
                ret[0] &= ~0x000F
                ret[0] |= ops[opN]["rval"]
                if ops[opN]["rtype"] == "r32": ret[0] += 0x0100
            elif flag == "rcc":
                condcode = nameMatch.group(2)
                for regex, cc in condcodes.items():
                    if re.match("("+regex+")$", condcode):
                        condcode = cc
                        break
                else:
                    raise Exception("\"j"+condcode+"\" is not recognized as a condition code.")
                ret[0] &= ~0x00F0
                ret[0] |= cc << 4                
            elif flag == "rsp":
                ret[0] &= ~0x00FF
                ret[0] |= 0xBB # 2x %P
            elif flag == "mvm":
                op0 = ops[0]
                op1 = ops[1]
                if op0["rtype"] == "r32": ret[0] += 0x0200
                if op1["rtype"] == "r32": ret[0] += 0x0100
                ret[0] &= ~0x00FF
                ret[0] |= op0["rval"] << 4
                ret[0] |= op1["rval"]
        
        print(cmd, ops)
        print([f"{x:04X}" for x in ret])
        print(relocs)
        print()
        
        return ret, relocs
    raise Exception("Could not find command \""+cmd+"\" in database.")
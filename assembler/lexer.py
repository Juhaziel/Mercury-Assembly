import re
import traceback

class Lexer:    
    @staticmethod
    def __lexlabel(text):
        symbol, chread = Lexer.lexsymbol(text)
        if not symbol: return "", 0
        if text[chread] != ":": return "", 0
        return symbol, chread+1
    
    @staticmethod
    def __lexcmd(text):
        text = str.lower(text)
        m = re.match(r"\s+(?P<cmd>\.?[a-z]\w*)", text)
        if not m:
            return "", 0
        cmd = m.group("cmd")
        return cmd, len(m.group(0))
    
    @staticmethod
    def __lexoperands(text):
        i = 0
        ops = []
        opraw = ""
        stringmode = False
        while i < len(text):
            c = text[i]
            if not stringmode and c in ";":
                break
            if not stringmode and c in "," and opraw != "":
                ops.extend(Lexer.lexliterals(opraw.strip()))
                opraw = ""
            elif not stringmode and c.isspace():
                if opraw == "": pass
                elif opraw[-1].isspace(): pass
                else: opraw += " "
            elif c in "\"\'":
                if opraw == "":
                    stringmode = c
                elif opraw[-1] == "\\":
                    pass
                elif c == stringmode:
                    stringmode = False
                opraw += c
            else:
                opraw += c
            i += 1
        
        if stringmode:
            raise Exception("Unbalanced string quotes.")
        if opraw != "":
            ops.extend(Lexer.lexliterals(opraw.strip()))
        return ops, i
    
    @staticmethod
    def isComment(text):
        if re.match(r"\s*(;.*)?$", text): return True
        return False
    
    @staticmethod
    def lexsymbol(text):
        text = str.lower(text)
        m = re.match(r"[a-z_\.@][\w_\.@]*", text)
        if not m: return "", 0
        return m.group(0), len(m.group(0))
    
    @staticmethod
    def leximm(text):
        mexpr, chread = Lexer.lexmath(text)
        if chread: return mexpr, "mexpr", chread

        lbl, chread = Lexer.lexsymbol(text)
        if chread: return lbl, "lbl", chread

        m = re.match(r"([01]+)b\b|([0-7]+)o\b|([0-9]+)d?\b|([0-9][0-9a-f]*)h\b", str.lower(text))
        if m:
            if m.group(1): return int(m.group(1), 2), "abs", len(m.group(0))
            if m.group(2): return int(m.group(2), 8), "abs", len(m.group(0))
            if m.group(3): return int(m.group(3), 10), "abs", len(m.group(0))
            if m.group(4): return int(m.group(4), 16), "abs", len(m.group(0))
        return None, "NAN", 0
    
    @staticmethod
    def lexreg(text):
        regid = "ABCDEGMLXYSPUVFZ"
        m = re.match(r"%(["+regid+"]{1,2})", text)
        if m:
            if len(m.group(1)) == 1: return regid.find(m.group(1)), "r16", len(m.group(0))
            base = regid.find(m.group(1)[1])
            adj = regid.find(m.group(1)[0])
            if adj != (base ^ 0b0001): return None, "NAR", 0
            return base, "r32", len(m.group(0))
        return None, "NAR", 0
    
    @staticmethod
    def lexliteral(text):
        if text[0:2] == "$(" and text[-1] == ")":
            text = text[2:-1]
            op = Lexer.lexliteral(text)
            op["ismem"] = True
        else:
            op = {"rtype":None, "itype":None, "ismem":False, "rval":None, "ival":None}
            reg, rtype, chread = Lexer.lexreg(text)
            text = text[chread:].strip()
            if chread:
                op["rtype"] = rtype
                op["rval"] = reg
                if len(text) > 1 and text[0] == "+": # Expect imm
                    text = text[1:].strip()
                    imm, itype, chread = Lexer.leximm(text)
                    text = text[chread:]
                    if not chread: raise Exception("Expected immediate value after register value.")
                    op["itype"] = itype
                    op["ival"] = imm
            else: # Expect imm
                imm, itype, chread = Lexer.leximm(text)
                text = text[chread:]
                if not chread: raise Exception("Expected operand, got nothing.")
                op["itype"] = itype
                op["ival"] = imm
            if len(text) != 0: raise Exception("Unknown element \""+text+"\" in operand.")
        return op
    
    @staticmethod
    def lexliterals(text):
        ops = []
        if text[0] == "\"":
            text = bytes(text[1:-1], "ascii").decode("unicode_escape")
            for c in text:
                if not c.isascii():
                    raise Exception("String literal contains non-ascii character \""+c+"\"")
                ops.append(Lexer.lexliteral(str(ord(c))))
        elif text[0] == "\'":
            text = bytes(text[1:-1], "ascii").decode("unicode_escape")
            for i in range(0, len(text), 2):
                if not text[i:i+2].isascii():
                    raise Exception("String literal contains non-ascii characters \'"+text[i:i+2]+"\'")
                if i + 1 < len(text):
                    ops.append(Lexer.lexliteral(str((ord(text[i]) << 8) | ord(text[i+1]))))
                else:
                    ops.append(Lexer.lexliteral(str(ord(text[i]))))
        else:
            text2 = ""
            i = 0
            while i < len(text):
                c = text[i]
                if c == "\"":
                    buffer = ""
                    while i < len(text):
                        i += 1
                        if text[i] == "\"":
                            if i == 0 or text[i] != "\\":
                                break
                        buffer += text[i]
                    buffer = bytes(buffer, "ascii").decode("unicode_escape")
                    if len(buffer) != 1: raise Exception ("Invalid literal \""+buffer+"\"")
                    text2 += str(ord(buffer))
                elif c == "\'":
                    buffer = ""
                    while i < len(text):
                        i += 1
                        if text[i] == "\'":
                            if i == 0 or text[i] != "\\":
                                break
                        buffer += text[i]
                    buffer = bytes(buffer, "ascii").decode("unicode_escape")
                    if len(buffer) not in [1,2]: raise Exception("Invalid literal \'"+buffer+"\'")
                    if len(buffer) == 1:
                        text2 += hex(ord(buffer))[2:]+"H"
                    else:
                        text2 += hex(ord(buffer[0]) << 8 | ord(buffer[1]))[2:]+"H"
                else:
                    text2 += c
                i += 1
            ops.append(Lexer.lexliteral(text2))
        return ops
    
    def lexmath(text):
        if text[0] != "{" or text[-1] != "}": return None, 0
        text = text[1:-1]
        nodes = []
        outstack = []
        opstack = []
        i = 0

        while i < len(text):
            if not text[i].isspace():
                imm, itype, chread = Lexer.leximm(text[i:])
                if chread:
                    i+=chread-1
                    outstack.insert(0, {"type":itype,"val":imm})
                elif text[i]=="(":
                    opstack.insert(0, "lpar")
                elif text[i]==")":
                    while True:
                        if len(opstack) == 0: raise Exception("Mismatched parentheses in mexpr")
                        op = opstack.pop(0)
                        if op == "lpar": break
                        outstack.insert(0, {"type":"op", "val":op["op"]})
                else:
                    op = text[i]
                    op2 = text[i:i+2]
                    precedence = 0
                    if op == "~":
                        if op2 == "~=":
                            op = op2
                            precedence = 6
                            i+=1
                        else:
                            precedence = 1
                    elif op in "*/%":
                        precedence = 2
                    elif op in "+-":
                        precedence = 3
                    elif op in "<>":
                        precedence = 5
                        if op2 == op*2:
                            op = op2
                            precedence = 4
                            i+=1
                        elif op2 == op+"=":
                            op = op2
                            i+=1
                    elif op2 == "==":
                        op = op2
                        precedence = 6
                        i+=1
                    elif op == "&": precedence = 7
                    elif op == "^": precedence = 8
                    elif op == "|": precedence = 9
                    op = {"op":op, "prec":precedence}
                    while True:
                        if len(opstack) == 0: break
                        o2 = opstack.pop(0)
                        if o2 == "lpar":
                            opstack.insert(0, o2)
                            break
                        if o2["prec"] <= precedence: outstack.insert(0, {"type":"op", "val":o2["op"]})
                        else:
                            opstack.insert(0, o2)
                            break
                    opstack.insert(0, op)
            i+=1
        while len(opstack) > 0:
            op = opstack.pop(0)
            if op == "lpar": raise Exception("Mismatched parentheseses in mexpr")
            outstack.insert(0, {"type":"op", "val":op["op"]})
        for v in outstack[::-1]:
            if v["type"] == "op":
                newnode = {"type":"op", "op":v["val"]}
                if v["val"] == "~":
                    newnode["nodes"] = nodes[-1:]
                    nodes[-1] = newnode
                else:
                    newnode["nodes"] = nodes[-2:]
                    nodes = nodes[:-2]
                    nodes.append(newnode)
            else:
                nodes.append(v)
        if len(nodes) > 1: raise Exception("Couldn't parse mexpr.")
        return nodes[0], i+2
    
    @staticmethod
    def lexline(text, ln=-1):
        if Lexer.isComment(text):
            return False, None
        
        data = {}
        data["ln"] = ln
        
        try:
            label, chread = Lexer.__lexlabel(text)
            data["label"] = label
            text = text[chread:]
            
            cmd, chread = Lexer.__lexcmd(text)
            data["cmd"] = cmd
            text = text[chread:]
            
            ops, chread = Lexer.__lexoperands(text)
            data["ops"] = ops
            text = text[chread:]
            
            if ops and not cmd:
                return False, "Cannot have operands with mnemonic"
        except Exception as e:
            return False, str(e)+"\n"+traceback.format_exc()
        
        if not Lexer.isComment(text):
            return False, "Expected comment, found '"+text+"'."
        return True, data
    
    @staticmethod
    def lextext(text):
        lines = []
        ln = 1
        for line in text.splitlines():
            success, linedata = Lexer.lexline(line, ln)
            if success:
                lines.append(linedata)
            else:
                if linedata:
                    raise Exception(str(ln)+": "+str(linedata))
            ln += 1

        return lines
    
    @staticmethod
    def lexfile(filename):
        with open(filename, "r") as f:
            return Lexer.lextext(f.read())
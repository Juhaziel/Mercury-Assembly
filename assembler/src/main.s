    .data
    .global main
    .weak val       ; Test weak overwriting
    .extern PI      ; Test global overwriting (should error, change to extern after)
val:    .dec 1      ; We expect this to be the used value.

    .text
    .extern hello
    .org 100h
main:
        PUSH %A
        PUSH PI
        CALL hello
        POP %A
        RET
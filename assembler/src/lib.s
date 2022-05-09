    .data
    .global PI          ; PI cannot be overwritten
    .weak val           ; val can be overwritten
        .set PI, 314159 ; Test global absolute values
val:    .dec 0          ; Test global labels

    .text
    .org 1000h
    .weak hello
hello:
        push val
        ret
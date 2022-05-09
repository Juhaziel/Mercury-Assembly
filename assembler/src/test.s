    .data
    .global mult, HELLO
    .extern externalvar
        
        .set HELLO, {5<<2}
        .set TEST, {3*HELLO}
        .string 'BEGIN\0'
        .dec HELLO, TEST
        .dec 'hi'
        .dec "hi", 'hello'

    .text
    .org 100h
mult:
    ; This function expects the two multiplied numbers to be in %A and %B.
    ; The 32 bit result will be stored in %AB
        PSH  %C
        PSH  %D
        PSH  %E
        MOV  %C, %A
        MOV  %D, %B
        XOR  %A, %A
        XOR  %B, %B
        MVI  %E, 10h
loop:   LSL  %A       ; 32b shift %AB
        LSL  %B
        ADC  %A, 0
        LSL  %C       ; Check the top bit of C and skip to _nc if 0
        JNC  _nc
        ADD  %B, %D   ; If not 0, 32b add D to AB
        ADC  %A, 0
_nc:    DEC  %E       ; Decrement and verify our counter variable
        JZ   loop     ; Goes back to the beginning of the loop if
                      ; our counter variable is not zero.
        POP  %E       ; Restore our borrowed registers
        POP  %D
        POP  %C
        RET           ; Return from function. The result is in %AB.
    .string 'end\0'
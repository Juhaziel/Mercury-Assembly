		.bss
		.org 100h
prime:  .res {10001}
result: .res {10001}
		
		.text
		.global main
		.org 10000h

main:   pushl %UV
		mov %UV, %SP
		push %A
		push %B
		push %C
		mov %A, 1
sieve:  inc %A
		cmp %A, 2
		jge s_end
		mov %B, $(%A+prime)
		jnz sieve
		mov %B, %A
loop:   add %B, %A
		cmp %B, 10000
		jge sieve
		mov $(%B+prime), 1
		jmp loop
s_end:  mov %A, 1
		mov %C, 0
ploop:  inc %A
		cmp %A, 10000
		jge end
		mov %B, $(%A+prime)
		jnz ploop
		mov $(%C+result), %A
		inc %C
		jmp ploop
end:    pop %C
		pop %B
		pop %A
		popl %UV
		ret
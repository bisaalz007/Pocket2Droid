.syntax unified
.cpu arm920t
.arm
.section .text
.global _start
_start:
    b reset
    b fail
    b fail
    b fail
    b fail
    b fail
    b fail
    b fail
reset:
    ldr r0, =0x30004000
    mov r1, #0
    mov r3, #4096
clear:
    str r1, [r0], #4
    subs r3, r3, #1
    bne clear
    ldr r0, =0x30004000
    ldr r1, =0xc02
    str r1, [r0]
    ldr r1, =0x30000c02
    add r4, r0, #0x2200
    str r1, [r4]
    ldr r4, =sequence
    ldr r5, =0x30018000
    ldr r3, =(sequence_end-sequence)/4
copy:
    ldr r1, [r4], #4
    str r1, [r5], #4
    subs r3, r3, #1
    bne copy
    mcr p15, 0, r0, c2, c0, 0
    mov r1, #1
    mcr p15, 0, r1, c3, c0, 0
    mov r1, #0x79
    ldr r2, =0x88018008
    ldr r5, =0x30018000
    mov pc, r5
sequence:
    mcr p15, 0, r1, c1, c0, 0
    mov pc, r2
    mov r1, #0x78
    ldr r2, =success
    mcr p15, 0, r1, c1, c0, 0
    mov r0, r0
    mov pc, r2
.ltorg
sequence_end:
success:
    ldr r1, =pass_message
    mov r0, #4
    swi 0x123456
    mov r0, #0x20
    ldr r1, =exit_success
    swi 0x123456
    b .
fail:
    ldr r1, =fail_message
    mov r0, #4
    swi 0x123456
    mov r0, #0x20
    ldr r1, =exit_failure
    swi 0x123456
    b .
.balign 4
exit_success: .word 0x20026, 0
exit_failure: .word 0x20026, 1
pass_message: .asciz "PASS cpu-mmu-enable\n"
fail_message: .asciz "FAIL cpu-mmu-enable\n"
.ltorg

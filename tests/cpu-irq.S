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
    b irq
    b fail
reset:
    ldr r0, =0xc0000078
    mcr p15, 0, r0, c1, c0, 0
    mov r5, #0
    ldr r0, =0x51000000
    mov r1, #100
    str r1, [r0, #0x3c]
    mov r1, #0x200000
    str r1, [r0, #8]
    mov r1, #0x100000
    str r1, [r0, #8]
    ldr r0, =0x4a000008
    mvn r1, #0x4000
    str r1, [r0]
    msr cpsr_c, #0x53
wait:
    cmp r5, #0
    beq wait
    cmp r5, #1
    bne fail
    ldr r1, =pass_message
    mov r0, #4
    swi 0x123456
    mov r0, #0x20
    ldr r1, =exit_success
    swi 0x123456
    b .
irq:
    mrs r0, cpsr
    and r0, r0, #0x3f
    cmp r0, #0x12
    bne fail
    ldr r0, =0x4a000000
    mov r1, #0x4000
    str r1, [r0]
    str r1, [r0, #0x10]
    mov r5, #1
    subs pc, lr, #4
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
pass_message: .asciz "PASS cpu-irq\n"
fail_message: .asciz "FAIL cpu-irq\n"
.ltorg

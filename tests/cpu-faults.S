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
    b abort_handler
    b fail
    b fail
    b fail
.macro expect reg, value
    ldr r12, =\value
    cmp \reg, r12
    bne fail
.endm
.macro put addr, value
    ldr r0, =\addr
    ldr r1, =\value
    str r1, [r0]
.endm
.macro check_abort count, fsr, far
    expect r10, \count
    expect r8, \fsr
    expect r9, \far
.endm
reset:
    ldr sp, =0x30010000
    ldr r0, =0x30004000
    mov r1, #0
    mov r2, #4096
clear_l1:
    str r1, [r0], #4
    subs r2, r2, #1
    bne clear_l1
    put 0x30004000, 0x00000c02
    put 0x30004c00, 0x30000c02
    put 0x30004440, 0x30000c22
    put 0x30004480, 0x30000402
    ldr r0, =0x30004000
    mcr p15, 0, r0, c2, c0, 0
    mov r0, #1
    mcr p15, 0, r0, c3, c0, 0
    mov r0, #0x79
    mcr p15, 0, r0, c1, c0, 0
    nop
    mov r10, #0
    /* A=0 still reports the original unaligned address on a fault. */
    ldr r0, =0x13000001
    ldr r1, [r0]
    check_abort 1, 5, 0x13000001
    str r1, [r0]
    check_abort 2, 5, 0x13000001
    ldr r0, =0x11000003
    ldr r1, [r0]
    check_abort 3, 0x19, 0x11000003
    str r1, [r0]
    check_abort 4, 0x19, 0x11000003
    ldr r0, =0x12000002
    ldrt r1, [r0]
    check_abort 5, 0xd, 0x12000002
    strt r1, [r0]
    check_abort 6, 0xd, 0x12000002
    /* A later ordinary aligned fault must not inherit old low address bits. */
    ldr r0, =0x13000000
    ldr r1, [r0]
    check_abort 7, 5, 0x13000000
    /* Map FCSE ROM, leave the low fault address unmapped in the PID region. */
    put 0x30004080, 0x3000a001
    ldr r0, =0x3000a000
    ldr r1, =0xff2
    mov r2, #16
fcse_rom:
    str r1, [r0], #4
    add r1, r1, #0x1000
    subs r2, r2, #1
    bne fcse_rom
    mov r0, #0
    mcr p15, 0, r0, c8, c7, 0
    mov r0, #0x02000000
    mcr p15, 0, r0, c13, c0, 0
    nop
    ldr r0, =0x00012000
    ldr r1, [r0]
    check_abort 8, 7, 0x02012000
    add r0, r0, #1
    str r1, [r0]
    check_abort 9, 7, 0x02012001
    mov r0, #0x7b
    mcr p15, 0, r0, c1, c0, 0
    ldr r0, =0x00012003
    ldr r1, [r0]
    check_abort 10, 1, 0x02012003
    mov r0, #0
    mcr p15, 0, r0, c13, c0, 0
    mov r0, #0x78
    mcr p15, 0, r0, c1, c0, 0
    ldr r1, =pass_message
    mov r0, #4
    swi 0x123456
    mov r0, #0x20
    ldr r1, =exit_success
    swi 0x123456
    b .
abort_handler:
    mrc p15, 0, r8, c5, c0, 0
    mrc p15, 0, r9, c6, c0, 0
    add r10, r10, #1
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
pass_message: .asciz "PASS cpu-faults\n"
fail_message: .asciz "FAIL cpu-faults\n"
.ltorg

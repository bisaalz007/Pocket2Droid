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
reset:
    ldr sp, =0x30010000
    /* Zero the L1 table, then section-map ROM and RAM. */
    ldr r0, =0x30004000
    mov r1, #0
    mov r2, #4096
clear_l1:
    str r1, [r0], #4
    subs r2, r2, #1
    bne clear_l1
    put 0x30004000, 0x00000c02
    put 0x30004c00, 0x30000c02
    /* coarse 4KiB page, fine 1KiB tiny page and two fault sections. */
    put 0x30004400, 0x30008001
    put 0x30008000, 0x30020ff2
    put 0x30004404, 0x30009003
    put 0x30009000, 0x30021033
    put 0x30004440, 0x30000c22
    put 0x30004480, 0x30000402
    put 0x30020000, 0x12345678
    put 0x30021000, 0x87654321
    put 0x30023000, 0xabcdef42
    ldr r0, =0x30004000
    mcr p15, 0, r0, c2, c0, 0
    mov r0, #1
    mcr p15, 0, r0, c3, c0, 0
    mov r0, #0x79
    mcr p15, 0, r0, c1, c0, 0
    nop
    nop
    ldr r0, =0x10000000
    ldr r1, [r0]
    expect r1, 0x12345678
    ldr r0, =0x10100000
    ldr r1, [r0]
    expect r1, 0x87654321
    /* Rewrite descriptor + invalidate must change the actual TCG load. */
    put 0x30008000, 0x30023ff2
    mov r0, #0
    mcr p15, 0, r0, c8, c7, 0
    ldr r0, =0x10000000
    ldr r1, [r0]
    expect r1, 0xabcdef42
    mov r10, #0
    ldr r0, =0x11000000
    ldr r1, [r0]
    expect r10, 1
    expect r8, 0x19
    expect r9, 0x11000000
    ldr r0, =0x12000000
    ldrt r1, [r0]
    expect r10, 2
    expect r8, 0xd
    expect r9, 0x12000000
    /* Precise partial STM: first beat writes; faulting beat and base do not. */
    put 0x30008000, 0x30023ff2
    put 0x30008004, 0
    mov r0, #0
    mcr p15, 0, r0, c8, c7, 0
    ldr r4, =0x10000ffc
    ldr r2, =0x55aa1234
    ldr r3, =0xdeadbeef
    stmia r4!, {r2, r3}
    expect r10, 3
    expect r8, 7
    expect r9, 0x10001000
    expect r4, 0x10000ffc
    ldr r0, =0x30023ffc
    ldr r1, [r0]
    expect r1, 0x55aa1234
    /* LDM retains a completed first load and leaves the faulting destination. */
    ldr r4, =0x10000ffc
    mov r2, #0
    ldr r3, =0x10203040
    ldmia r4!, {r2, r3}
    expect r10, 4
    expect r2, 0x55aa1234
    expect r3, 0x10203040
    expect r4, 0x10000ffc
    expect r8, 7
    expect r9, 0x10001000
    /* A=1 must fault using the original unaligned VA, without rotation. */
    mov r0, #0x7b
    mcr p15, 0, r0, c1, c0, 0
    ldr r0, =0x30020001
    ldr r1, [r0]
    expect r10, 5
    expect r8, 1
    expect r9, 0x30020001
    mov r0, #0x79
    mcr p15, 0, r0, c1, c0, 0
    /* FCSE: executing low ROM and VA0x11000 use the PID-modified address. */
    put 0x30004080, 0x3000a001
    ldr r0, =0x3000a000
    ldr r1, =0xff2
    mov r2, #16
fcse_rom:
    str r1, [r0], #4
    add r1, r1, #0x1000
    subs r2, r2, #1
    bne fcse_rom
    put 0x3000a044, 0x30022ff2
    put 0x30022000, 0x13579bdf
    mov r0, #0
    mcr p15, 0, r0, c8, c7, 0
    mov r0, #0x02000000
    mcr p15, 0, r0, c13, c0, 0
    nop
    ldr r0, =0x00011000
    ldr r1, [r0]
    expect r1, 0x13579bdf
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
pass_message: .asciz "PASS cpu-mmu\n"
fail_message: .asciz "FAIL cpu-mmu\n"
.ltorg

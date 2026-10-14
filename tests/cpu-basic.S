.syntax unified
.cpu arm920t
.arm
.section .text
.global _start
_start:
    b reset
    b fail
    b swi_handler
    b fail
    b fail
    b fail
    b fail
    b fail

.macro expect reg, value
    ldr r12, =\value
    cmp \reg, r12
    bne fail
.endm

reset:
    mrs r0, cpsr
    and r0, r0, #0xff
    expect r0, 0xd3
    mrc p15, 0, r0, c0, c0, 0
    expect r0, 0x41129200
    mrc p15, 0, r0, c0, c0, 1
    expect r0, 0x0d172172
    mrc p15, 0, r0, c1, c0, 0
    expect r0, 0x78
    ldr r0, =0x30020044
    ldr r1, [r0]
    expect r1, 0xde12de34
    ldrh r1, [r0, #4]
    expect r1, 240
    ldrh r1, [r0, #6]
    expect r1, 320
    ldrh r1, [r0, #8]
    expect r1, 16
    /* Independent IRQ/SVC stacks and SPSR exception return. */
    ldr sp, =0x30010000
    msr cpsr_c, #0xd2
    ldr sp, =0x30011000
    msr cpsr_c, #0xd3
    expect sp, 0x30010000
    msr cpsr_c, #0xd2
    expect sp, 0x30011000
    msr cpsr_c, #0xdf
    swi 0x42
    mrs r0, cpsr
    and r0, r0, #0x1f
    expect r0, 0x1f
    expect r8, 0x55
    msr cpsr_c, #0xd3
    /* ARMv4 unaligned word loads rotate the aligned word. */
    ldr r1, =0x30012000
    ldr r0, =0x44332211
    str r0, [r1]
    ldr r0, [r1, #1]
    expect r0, 0x11443322
    ldr r0, [r1, #2]
    expect r0, 0x22114433
    ldr r0, [r1, #3]
    expect r0, 0x33221144
    ldr r0, =0xaabbccdd
    str r0, [r1, #3]
    ldr r0, [r1]
    expect r0, 0xaabbccdd
    /* Exact ROM memcpy uses a PLD encoding in ARMv4T's NV space. */
    .word 0xf5d1f000
    ldr r0, =thumb_start
    bx r0

.thumb
.thumb_func
thumb_start:
    movs r0, #23
    adds r0, #19
    cmp r0, #42
    bne thumb_fail
    ldr r1, =arm_return
    bx r1
thumb_fail:
    ldr r1, =fail
    bx r1
.arm
arm_return:
    /* Execute RAM, replace its instruction, flush I-cache and execute again. */
    ldr r4, =0x30013000
    ldr r0, =0xe3a00001
    str r0, [r4]
    ldr r0, =0xe12fff1e
    str r0, [r4, #4]
    mov lr, pc
    bx r4
    expect r0, 1
    ldr r0, =0xe3a00002
    str r0, [r4]
    mcr p15, 0, r0, c7, c5, 0
    mov lr, pc
    bx r4
    expect r0, 2
    ldr r1, =flash_probe_start
    ldr r2, =0x30014000
    ldr r3, =(flash_probe_end - flash_probe_start) / 4
flash_copy:
    ldr r0, [r1], #4
    str r0, [r2], #4
    subs r3, r3, #1
    bne flash_copy
    ldr r2, =0x30014000
    mov lr, pc
    bx r2
    expect r0, 0
    ldr r1, =pass_message
    mov r0, #4
    swi 0x123456
    mov r0, #0x20
    ldr r1, =exit_success
    swi 0x123456
    b .
swi_handler:
    mov r8, #0x55
    movs pc, lr
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
pass_message: .asciz "PASS cpu-basic\n"
fail_message: .asciz "FAIL cpu-basic\n"
.ltorg
.balign 4
/* Run from RAM while the low identification words are selected. */
flash_probe_start:
    /* ROM array -> unlock -> autoselect -> reset, host bytes immutable. */
    ldr r4, =0xaaaa
    ldr r5, =0x5554
    ldr r0, =0xaaaa
    mov r6, #0
    ldr r7, [r6, #4]
    strh r0, [r4]
    ldr r0, =0x5555
    strh r0, [r5]
    ldr r0, =0x9090
    strh r0, [r4]
    mov r0, #0
    ldrh r1, [r0]
    cmp r1, #1
    bne flash_fail
    ldrh r1, [r0, #2]
    ldr r2, =0x225b
    cmp r1, r2
    bne flash_fail
    /* Device Emulator selects low ID words, retaining the other ROM bytes. */
    ldr r1, [r0, #4]
    cmp r1, r7
    bne flash_fail
    ldr r1, =0xf0f0
    strh r1, [r0]
    mov r0, #0
    bx lr
flash_fail:
    mov r0, #1
    bx lr
.ltorg
flash_probe_end:

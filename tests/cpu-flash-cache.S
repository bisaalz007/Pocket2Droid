.syntax unified
.cpu arm920t
.arm
.section .text
.global _start
_start:
    b main
    b id_header

/* Reenter a cached header before, during, and after flash identification.
 * The ID word 0x225b0001 is predicated CS; clear carry before executing it
 * so the guest must advance to the unchanged branch at ROM offset four.
 */
.org 0x10000
main:
    cmp r6, #0
    beq warm_header
    cmp r6, #1
    beq query
    cmp r6, #3
    beq pass
    b fail
warm_header:
    mov r6, #1
    b _start
query:
    mov r6, #2
    ldr r4, =0xaaaa
    ldr r5, =0x5554
    ldr r0, =0xaaaa
    strh r0, [r4]
    ldr r0, =0x5555
    strh r0, [r5]
    ldr r0, =0x9090
    strh r0, [r4]
    mov r0, #0
    cmp r0, #1
    b _start
id_header:
    cmp r6, #2
    bne fail
    ldr r1, =0x30010000
    ldr r0, =0x1d001d00
    str r0, [r1]
    mov r1, #0
    ldr r0, =0xf0f0
    strh r0, [r1]
    mov r6, #3
    mov r0, #0
    cmp r0, #1
    b _start
pass:
    ldr r1, =0x30010000
    ldr r0, [r1]
    ldr r2, =0x1d001d00
    cmp r0, r2
    bne fail
    ldr r0, =0x600d600d
    str r0, [r1, #4]
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
pass_message: .asciz "PASS cpu-flash-cache\n"
fail_message: .asciz "FAIL cpu-flash-cache\n"
.ltorg

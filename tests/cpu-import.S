.syntax unified
.cpu arm920t
.arm
.global _start
_start:
    ldr sp, =0x30010000
    ldr r1, =0x30040000
    ldr r2, =0x00000c12
    str r2, [r1]
    ldr r2, =0x30000c12
    ldr r3, =0x2000
    str r2, [r1,r3]
    ldr r2, =0x50000c12
    ldr r3, =0x1400
    str r2, [r1,r3]
    mcr p15,0,r1,c2,c0,0
    mov r0,#3
    mcr p15,0,r0,c3,c0,0
    mrc p15,0,r0,c1,c0,0
    ldr sp, =0x80010000
    orr r0,r0,#1
    mcr p15,0,r0,c1,c0,0
    nop
    nop
    ldr r4, =0x80030000
    ldr r0, =0xe3a00001
    str r0,[r4]
    ldr r0, =0xe12fff1e
    str r0,[r4,#4]
    mov lr,pc
    bx r4
    cmp r0,#1
    bne fail
    ldr r5, =0x80008000
    ldr r0, =1068
    strh r0,[r5]
    adr r1,filename
    add r2,r5,#36
    mov r3,#34
copy_name:
    ldrb r0,[r1],#1
    strb r0,[r2],#1
    subs r3,r3,#1
    bne copy_name
    mov r0,#34
    strh r0,[r5,#34]
    ldr r6, =0x500f4000
    ldr r0,=0x30008000
    str r0,[r6]
    mov r0,#6
    str r0,[r6,#4]
    ldr r0,[r6,#12]
    cmp r0,#0
    bne fail
    mov r0,#8
    str r0,[r5,#16]
    mov r0,#64
    str r0,[r5,#20]
    str r4,[r5,#24]
    mov r0,#7
    str r0,[r6,#4]
    ldr r0,[r6,#12]
    cmp r0,#0
    bne fail
    mov lr,pc
    bx r4
    cmp r0,#2
    bne fail
    /* First transfer chunk rewrites the section descriptor of later chunks.
     * The importer must use the initially validated RAM spans, never retranslate
     * into the new MMIO mapping partway through this single DMA operation.
     */
    ldr r0,=1032
    str r0,[r5,#16]
    mov r0,#128
    str r0,[r5,#20]
    ldr r0,=0x80041ffc
    str r0,[r5,#24]
    mov r0,#7
    str r0,[r6,#4]
    ldr r7,[r6,#12]
    mrc p15,0,r0,c1,c0,0
    bic r0,r0,#1
    mcr p15,0,r0,c1,c0,0
    nop
    nop
    cmp r7,#0
    bne fail
    ldr r0,=0x30042400
    ldr r0,[r0]
    ldr r1,=0x12345678
    cmp r0,r1
    bne fail
    mov r0,#4
    adr r1,passed
    svc 0x123456
    b exit
fail:
    mov r0,#4
    adr r1,failed
    svc 0x123456
exit:
    mov r0,#0x18
    ldr r1,=0x20026
    svc 0x123456
.align 2
filename:
    .hword 82,97,103,105,110,103,84,104,117,110,100,101,114,46,99,97,98
passed: .asciz "PASS cpu-import-mmu-native-invalidation\n"
failed: .asciz "FAIL cpu-import-mmu-native-invalidation\n"

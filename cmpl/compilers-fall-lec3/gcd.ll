target triple = "x86_64-unknown-linux-gnu"

define i32 @gcd(i32 %a, i32 %b) {
entry:
  br label %cond

cond:
  %a.phi = phi i32 [ %a, %entry ], [ %b.phi, %body ]
  %b.phi = phi i32 [ %b, %entry ], [ %t, %body ]
  %done  = icmp eq i32 %b.phi, 0
  br i1 %done, label %exit, label %body

body:
  %t = srem i32 %a.phi, %b.phi
  br label %cond

exit:
  ret i32 %a.phi
}

@fmt = private unnamed_addr constant [18 x i8] c"gcd(12, 15) = %d\0A\00", align 1

declare i32 @printf(ptr, ...)

define i32 @main() {
entry:
  %r = call i32 @gcd(i32 12, i32 15)
  call i32 (ptr, ...) @printf(ptr @fmt, i32 %r)
  ret i32 0
}

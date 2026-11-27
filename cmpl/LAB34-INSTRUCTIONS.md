# Лабораторные 3 и 4 — как это выполнялось на машине пользователя
# и как воспроизвести (Ubuntu, y пользователя: ~/cmpl/lab3, ~/cmpl/lab4)

Статус: лаба 3 выполнена и проверена; лаба 4 выполнена и проверена.
Ниже — фактический ход выполнения и набор правок, которые понадобились
(на LLVM 24 из ~/opt/clang, собранном в лабе 1).

Отчёты:
- compilers-fall-lec3/lab3/LAB3.md
- compilers-fall-lec4/lab4/LAB4.md

────────────────────────────────────────────────────────────
## Лабораторная 3 — gcd в LLVM IR
────────────────────────────────────────────────────────────
Каталог `~/cmpl/lab3` рядом с материалами лекции.

1) Создать `~/cmpl/lab3/gcd.ll` (ручной SSA-вариант; в ветке:
   `cmpl/compilers-fall-lec3/gcd.ll`, лежит рядом с `gcd.c`):

```
cat > ~/cmpl/lab3/gcd.ll <<'EOF'
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
EOF
```

2) Запустить (PATH — на clang из лабы 1):

```
export PATH=$HOME/opt/clang/bin:$PATH
which clang lli
lli gcd.ll                       # -> gcd(12, 15) = 3
clang gcd.ll -o gcd && ./gcd     # -> gcd(12, 15) = 3
clang gcd.c -o gcd_c && ./gcd_c  # -> gcd(12, 15) = 3
```

3) Сравнение с выводом clang'а:

```
cd ~/cmpl/lab3
clang -O0 -S -emit-llvm gcd.c -o gcd-clang-O0.ll
clang -O1 -S -emit-llvm gcd.c -o gcd-clang-O1.ll
grep -nE 'alloca|phi' gcd-clang-O1.ll
```

Фактический вывод grep:

```
14:  %5 = phi i32 [ %6, %4 ], [ %0, %2 ]
15:  %6 = phi i32 [ %7, %4 ], [ %1, %2 ]
21:  %10 = phi i32 [ %0, %2 ], [ %6, %4 ]
30:  %2 = phi i32 [ %3, %1 ], [ 12, %0 ]
31:  %3 = phi i32 [ %4, %1 ], [ 15, %0 ]
```

(`alloca` нет — SSA после mem2reg; ручной gcd.ll структурно совпадает
с выводом -O1: phi в заголовке, icmp eq, srem, br i1.)

────────────────────────────────────────────────────────────
## Лабораторная 4 — BOOLEAN → Int1 в кодогенерации
────────────────────────────────────────────────────────────
Каталог `~/cmpl/lab4/tinylang` рядом с материалами лекции.

Правки, которые потребовались (на LLVM 24; на LLVM 17 собирается
исходный код + BOOLEAN-патч):

| Файл | Правка | Зачем |
|------|--------|-------|
| lib/CodeGen/CGModule.cpp | `if (Ty->getName() == "BOOLEAN") return Int1Ty;` в convertType | задание «BOOLEAN → Int1» |
| lib/CodeGen/CGModule.cpp | `this->Mod = Mod;` первой строкой `run()` | курсовой баг: поле Mod никогда не инициализировалось, `getModuleDeclaration()` возвращал мусор → любой доступ к глобальной BOOLEAN-переменной из процедуры падал в `report_fatal_error("Nested procedures not yet supported")` |
| lib/CodeGen/CGProcedure.cpp | `PHINode::Create(..., llvm::InsertPosition(BB->begin()))` (и `InsertPosition(BB)` для пустого блока) вместо `&BB->front()` | LLVM ≥ 18: Instruction* больше не конвертируется в InsertPosition |
| tools/driver/Driver.cpp | `lookupTarget(Triple, ErrMsg)` вместо `lookupTarget(Triple.getTriple(), ErrMsg)` | StringRef-оверлоад убран |
| tools/driver/Driver.cpp | `createMCSubtargetInfo(Triple, codegen::getCPUStr(), codegen::getFeaturesStr())` вместо StringRef первого аргумента | первый аргумент — const Triple& |
| CMakeLists.txt | `include_directories("${LLVM_INCLUDE_DIRS}")` вместо `"${LLVM_BINARY_DIR}/include" "${LLVM_INCLUDE_DIR}"` | LLVM_INCLUDE_DIR не определён в установленном дереве LLVM; LLVM_INCLUDE_DIRS — корректная переменная |
| lab/tests/boolean-var.mod | тело модуля обёрнуто в процедуру `Main()` | операторы на уровне MODULE парсятся, но НЕ кодогенерируются (`CGModule::run` игнорирует `Mod->getStmts()`) |

Сборка:

```
cd ~/cmpl/lab4/tinylang && mkdir -p build && cd build
cmake -G Ninja -DLLVM_DIR=$HOME/opt/clang/lib/cmake/llvm -DCMAKE_BUILD_TYPE=Release ..
ninja tinylang          # -> tools/driver/tinylang
```

Прогон всех тестов:

```
cd ~/cmpl/lab4/lab/tests
TL=~/cmpl/lab4/tinylang/build/tools/driver/tinylang
for t in *.mod; do "$TL" --emit-llvm -o "${t%.mod}.ll" "$t"; done
grep -E 'i1' boolean-phi.ll
grep -E '^(if.body|else.body|after.if):' if-then-else.ll
grep -E '^(while.cond|while.body|after.while):' while-blocks.ll
```

Фактически: все 7 тестов выдали IR без диагностики.

* boolean-phi.ll: `define i1 @_t7BoolPhi6Toggle(i64 %n)`,
  `phi i1 [ %3, %while.body ]`, `xor i1 %0, true`, `br i1 %2, ...`
* boolean-global.ll: `@_t10BoolGlobal4flag = private global i1`,
  `store i1 true, ptr @_t10BoolGlobal4flag, align 1`
* if-then-else.ll: метки `if.body:`, `else.body:`, `after.if:` — 3 блока
* while-blocks.ll: метки `while.cond:`, `while.body:`, `after.while:` — 3 блока

Полные выводы — в `compilers-fall-lec4/lab4/LAB4.md` (приложение).

Ограничения (честно): module-level операторы не кодогенерируются;
вызовы процедур — `report_fatal_error("not implemented")` (не входит
в задание); использование до присваивания не диагностируется.

Бинарные артефакты (build/, *.o, *.s) в репозиторий не кладутся.

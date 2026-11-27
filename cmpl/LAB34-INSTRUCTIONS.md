# Что сделать вам на вашем компьютере (lab3 + lab4, LLVM-части)
# Предпосылка: LLVM собран в лабе 1 на вашей машине (например, ~/opt/clang).
# Файлы лежат в ветке arena/49580c38-lmarena рядом с материалами лекций.

Важно: все файлы подготовлены и лежат в тех же папках, что и материалы.
Вся проверка через LLVM (запуск gcd.ll, сборка tinylang, эмиссия IR) — у вас.

────────────────────────────────────────────────────────────
## Лабораторная 3 — gcd в LLVM IR (cmpl/compilers-fall-lec3/)
────────────────────────────────────────────────────────────
1) Проверить, что clang/lli из вашей сборки видны:
   export PATH=$HOME/opt/clang/bin:$PATH
   clang --version
   lli --version

2) Положить gcd.ll рядом с gcd.c (в корень lab3), если его там нет:
   копия — в ветке: cmpl/compilers-fall-lec3/gcd.ll
   (или: mkdir -p ~/cmpl/lab3 && cp gcd.ll ~/cmpl/lab3/)

3) Запустить:
   cd ~/cmpl/lab3        # или .../cmpl/compilers-fall-lec3
   lli gcd.ll
   # или собрать в ELF:
   clang gcd.ll -o gcd && ./gcd
   clang gcd.c -o gcd_c && ./gcd_c
   Ожидаем в обоих случаях: gcd(12, 15) = 3

4) Сгенерировать референс clang'а для сравнения стиля IR:
   clang -O0 -S -emit-llvm gcd.c -o gcd-clang-O0.ll
   clang -O1 -S -emit-llvm gcd.c -o gcd-clang-O1.ll
   gcd-clang-O0.ll: alloca/load/store, блоки while.cond/while.body.
   gcd-clang-O1.ll: память убрана mem2reg, phi в заголовке — как в gcd.ll.
   Сравните структуру с gcd.ll (блоки cond/body/exit, phi %a.phi/%b.phi).

────────────────────────────────────────────────────────────
## Лабораторная 4 — кодогенерация BOOLEAN→Int1
────────────────────────────────────────────────────────────
5) Сборка tinylang (та же, что в лабе 2):
   cd ~/cmpl/lab4/tinylang    # или .../compilers-fall-lec4/tinylang
   mkdir -p build && cd build
   cmake -G Ninja \
         -DLLVM_DIR=$HOME/opt/clang/lib/cmake/llvm \
         -DCMAKE_BUILD_TYPE=Release ..
   ninja tinylang
   # готово: build/tools/driver/tinylang

   Если ваш LLVM не в ~/opt/clang — укажите LLVM_DIR в его каталог
   (.../lib/cmake/llvm, где лежит LLVMConfig.cmake).
   Найти: find ~ -name LLVMConfig.cmake 2>/dev/null

6) Проверка BOOLEAN→Int1 (пункт «добавить поддержку типа BOOLEAN→Int1»):
   cd ../lab/tests
   for m in boolean-var boolean-global boolean-param-ret boolean-expr boolean-phi; do
     ../../tinylang/build/tools/driver/tinylang --filetype=asm --emit-llvm \
        -o $m.ll $m.mod
   done
   grep -E 'i1' boolean-phi.ll
   Ожидаем в boolean-phi.ll: define i1 @..., phi i1, xor i1, br i1.
   boolean-global.ll:  @_t... = private global i1 ...
   boolean-param-ret.ll: define i1 @_t...(i1 %b) ...

7) Подсчёт базовых блоков:
   ../../tinylang/build/tools/driver/tinylang --filetype=asm --emit-llvm \
      -o if-then-else.ll if-then-else.mod
   grep -E '^(if.body|else.body|after.if):' if-then-else.ll
   → ожидаем 3 метки (if.body, else.body, after.if)

   ../../tinylang/build/tools/driver/tinylang --filetype=asm --emit-llvm \
      -o while-blocks.ll while-blocks.mod
   grep -E '^(while.cond|while.body|after.while):' while-blocks.ll
   → ожидаем 3 метки (while.cond, while.body, after.while)

   Сохраните .ll рядом (lab4/) и вставьте в LAB4.md или покажите на защите.

────────────────────────────────────────────────────────────
## Патчи, уже применённые в репозитории (для справки)
────────────────────────────────────────────────────────────
| Файл | Патч | Зачем |
|------|-------|-------|
| cmpl/compilers-fall-lec4/tinylang/lib/CodeGen/CGModule.cpp | BOOLEAN → Int1Ty в convertType | задание «BOOLEAN → Int1» |
| cmpl/compilers-fall-lec4/tinylang/lib/CodeGen/CodeGenerator.cpp | setTargetTriple: Triple для LLVM ≥ 19, StringRef для ≤ 18 (по LLVM_VERSION_MAJOR) | совместимость с API обеих веток LLVM |
| cmpl/compilers-fall-lec4/tinylang/CMakeLists.txt | include_directories(${LLVM_INCLUDE_DIRS}) | хедеры и при build-, и при install-дереве LLVM |
| cmpl/compilers-fall-lec2/tinylang/CMakeLists.txt | то же самое | то же |
| cmpl/compilers-fall-lec2/lab/tests/*.mod | тесты для заданий lab2 (прогнаны, лог: lab2/run-output.log) | лаба 2 |
| cmpl/compilers-fall-lec3/gcd.ll | ручной gcd на LLVM IR (без комментариев) | лаба 3 |
| cmpl/compilers-fall-lec4/lab/tests/*.mod | тесты BOOLEAN / if / while | лаба 4 |

Бинарные артефакты (build/, *.o, *.s, исполняемые) в репозиторий не кладутся.

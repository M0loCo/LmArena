# Лабораторные 3 и 4 — полный отчёт и шпаргалка к сдаче

Операции: лаба 3 — LLVM IR вручную; лаба 4 — кодогенерация BOOLEAN→i1 в TinyLang.
Всё, что ниже помечено «проверено» — реально выполнялось на машине пользователя
(Ubuntu, clang/LLVM 24.0.0git из лабы 1, установлен в `~/opt/clang`;
`cmake 4.2.3`, `ninja 1.13.2`, `gcc 15.2.0`). Ничего не выдумано: все выводы
скопированы из терминала.

Раскладка на машине пользователя: `~/cmpl/lab3` и `~/cmpl/lab4` (плоская,
рядом с материалами лекций). В этом репозитории те же файлы лежат в
`cmpl/compilers-fall-lec3/…` и `cmpl/compilers-fall-lec4/…`.

---

## 0. Что сделано — одной таблицей

| Работа | Что | Результат |
|--------|-----|-----------|
| Лаба 3 | `gcd.c` переписан на чистый SSA LLVM IR (`gcd.ll`), объяснение трансляции аргументов и цикла | `lli gcd.ll` и `clang gcd.ll -o gcd` → `gcd(12, 15) = 3` |
| Лаба 3 | Сравнение с IR от `clang -O0/-O1` | `-O0`: alloca/load/store; `-O1`: phi (mem2reg), структура = ручному `gcd.ll` |
| Лаба 4 | Добавлена поддержка BOOLEAN→i1 в кодогенераторе | Все 7 тестов эмитят IR с `i1`; `boolean-phi.ll`: `phi i1`, `xor i1`, `br i1` |
| Лаба 4 | Собрана tinylang против LLVM 24 | потребовалось 5 точечных правок (см. §4.3) — одна из них (неинициализированный `CGModule::Mod`) — курсовой баг с вводящим в заблуждение сообщением |
| Лаба 4 | Подсчёт базовых блоков if/while подтверждён выводом | `if-then-else`: `if.body`/`else.body`/`after.if`; `while-blocks`: `while.cond`/`while.body`/`after.while` |

Отчёты по частям: `compilers-fall-lec3/lab3/LAB3.md`, `compilers-fall-lec4/lab4/LAB4.md`
(в LAB4.md — приложение с полными выводами всех 7 тестов).

---

## 1. Лаба 3 · что показывают на сдаче

Файлы: `gcd.c` (материал лекции, не трогали), `gcd.ll` (ручной IR, лежит рядом).

### 1.1 Исходный `gcd.c`

```c
int gcd(int a, int b)
{
    while (b != 0) { int t = a % b; a = b; b = t; }
    return a;
}
```

### 1.2 `gcd.ll` — что говорить по каждой конструкции

```llvm
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
```

Говорить так:

* **Типы**: `int` → `i32` (проверка на лекции), условие — `i1`, регистры строго
  типизированы, «случайно сложить i32 и i64 нельзя».
* **Аргументы**: сигнатура `i32 (i32, i32)` — функция первого класса; `call`
  передаёт по значению; по SysV AMD64 первые целочисленные аргументы — в
  `%rdi`, `%rsi`; фиксируется `target triple` + `datalayout`.
* **SSA**: нет «присваивания»; `a := b; b := t` выражено phi-функциями.
  Имена `%a.phi` — для читаемости, машинный код их не видит.
* **CFG**: `entry → cond → body ↺ / → exit`. `cond` — заголовок цикла:
  phi сливает значения из `entry` (первая итерация) и `body` (перенос).
  phi обязаны иметь вход на каждого предшественника блока ровно один
  (иначе верификатор: `PHINode should have one entry for each predecessor`).
* **`icmp eq i32 %b.phi, 0` → `i1`** — условие для `br i1`.
* **`srem`** — знаковый остаток, ровно `%` в C для `int`.

### 1.3 Проверка (всё выполнено, выводы реальные)

```bash
cd ~/cmpl/lab3
export PATH=$HOME/opt/clang/bin:$PATH
which clang lli          # /home/phl3/opt/clang/bin/clang, .../lli
lli gcd.ll               # -> gcd(12, 15) = 3
clang gcd.ll -o gcd && ./gcd   # -> gcd(12, 15) = 3
clang gcd.c -o gcd_c && ./gcd_c # -> gcd(12, 15) = 3
clang -O0 -S -emit-llvm gcd.c -o gcd-clang-O0.ll
clang -O1 -S -emit-llvm gcd.c -o gcd-clang-O1.ll
grep -nE 'alloca|phi' gcd-clang-O1.ll
```

Реальный вывод `grep`:

```
14:  %5 = phi i32 [ %6, %4 ], [ %0, %2 ]
15:  %6 = phi i32 [ %7, %4 ], [ %1, %2 ]
21:  %10 = phi i32 [ %0, %2 ], [ %6, %4 ]
30:  %2 = phi i32 [ %3, %1 ], [ 12, %0 ]
31:  %3 = phi i32 [ %4, %1 ], [ 15, %0 ]
```

`alloca` нет — цикл уже в SSA (mem2reg отработал). Отличие от ручного
`gcd.ll` — только нумерованные регистры и склейка `main`.

### 1.4 Частые вопросы на сдаче — готовые ответы

* **Что такое SSA?** Каждое SSA-значение определяется ровно один раз;
  все использования ссылаются на это единственное определение.
* **Что такое phi?** Инструкция только первой в блоке, выбирает значение
  по тому, из какого предшественника пришёл поток. Пара `[value, pred]` на
  каждого предшественника.
* **Почему phi именно в заголовке цикла?** Потому что `cond` имеет двух
  предшественников (`entry`, `body`) — точки слияния SSA-определений.
* **Чем `-O0` отличается от `-O1`?** -O0: `alloca` под локалы + load/store
  (mem2reg потом это уберёт); -O1: сразу phi — как наш ручной файл.
* **Почему не `sdiv`, а `srem`?** Нужен остаток (`%`), а не частное.
* **Зачем `target triple`?** Фиксирует ABI: какой datalayout, какие регистры,
  как вызываются функции.
* **Можно ли без `lli`?** Да: `clang gcd.ll -o gcd` — clang сам ассемблирует
  IR в машинный код (показано).

---

## 2. Лаба 4 · что показывают на сдаче

### 2.1 Конвейер (говорить по диаграмме)

```
Driver (tools/driver/Driver.cpp)
  → Parser::parse()          (AST: ModuleDeclaration → Decls/Stmts)
  → Sema                     (типы, BOOLEAN зарегистрирован, TRUE/FALSE — предобъявленные константы)
  → CodeGenerator::run       (CodeGenerator.{h,cpp}, фасад)
      → CGModule::run        (CGModule.{h,cpp}: типы, mangleName, globals, цикл по ProcedureDeclaration)
          → CGProcedure::run (CGProcedure.{h,cpp}: Function, entry-блок, SSA-карта)
```

* **SSA без mem2reg**: локалы не идут в `alloca`; напрямую в карте
  `CurrentDef[BB].Defs[Decl] = Value*`. На слиянии потоков phi создаются
  на лету алгоритмом Braun et al. 2013 («seal blocks»):
  `readLocalVariable` → нет значения → `readLocalVariableRecursive`;
  блок не запечатан → `addEmptyPhi` (+ запомнить в `IncompletePhis`);
  запечатан → phi с операндами из всех предшественников → `optimizePhi`
  (тривиальные phi выкидываются каскадно). `sealBlock(BB)` — после того,
  как новых предшественников не появится.

### 2.2 Задание: BOOLEAN → Int1 — что именно меняли

В `CGModule::convertType` добавили ветку:

```cpp
if (Ty->getName() == "BOOLEAN")
  return Int1Ty;
```

Всё остальное уже работало через `i1` и не требовало правок:
`Int1Ty` создавался в `initialize()`; булевы литералы по `ConstantInt` → `i1`;
`AND/OR/NOT` → `and/or/xor` i1; `icmp` → `i1`; условия `IF/WHILE`
через `CreateCondBr` требуют `i1`; BOOLEAN зарегистрирован в `Sema`.

Автоматически заработало производное (всё идёт через `convertType`/`mapType`):
локальные и глобальные BOOLEAN-переменные, BOOLEAN-параметры и возвраты
(`i1` в сигнатуре), VAR-параметры (указатель на `i1`).

### 2.3 Правки, которые потребовались (назвать на сдаче — это подтверждает честность)

1. `CGModule.cpp`: `this->Mod = Mod;` первой строкой `CGModule::run(...)`.
   Курсовой баг: поле `Mod` никогда не присваивалось (ctor `: M(M)` только),
   `getModuleDeclaration()` возвращал мусор → ЛЮБОЙ доступ к глобальной
   переменной из процедуры падал с `LLVM ERROR: Nested procedures not yet supported`.
   Сообщение вводит в заблуждение — дело не во вложенных процедурах.
2. `CGProcedure.cpp` (`addEmptyPhi`): LLVM ≥ 18 — `Instruction*` не
   конвертируется в `InsertPosition`; исправлено на
   `llvm::InsertPosition(BB->begin())` / `InsertPosition(BB)`. В репозитории
   стоит `#if LLVM_VERSION_MAJOR >= 18` guard → под LLVM 17 собирается
   исходный вариант.
3. `Driver.cpp`: StringRef-оверлоад `lookupTarget` убран → осталось
   `lookupTarget(Triple, ErrMsg)`; `createMCSubtargetInfo(Triple, CPUStr, Features)`
   (первый аргумент — `Triple`). Совместимо и с LLVM 17.
4. `CMakeLists.txt`: `include_directories("${LLVM_INCLUDE_DIRS}")` вместо
   `"${LLVM_BINARY_DIR}/include" "${LLVM_INCLUDE_DIR}"` (старая переменная
   просто не определена в установленном дереве LLVM).
5. `lab/tests/boolean-var.mod`: тело модуля завёрнуто в `PROCEDURE Main()`,
   потому что **операторы на уровне MODULE не кодогенерируются**
   (`CGModule::run` читает только `getDecls()`; `Mod->getStmts()` игнорируется).

Эти правки в репозитории — в той же форме (с guard).

### 2.4 Три главных вопроса — готовые ответы

* **Сколько базовых блоков у if-then-else?** 3 новых: `if.body`, `else.body`,
  `after.if` (без else — 2). Условие вычисляется в предшествующем блоке.
* **Сколько у while?** 3 новых: `while.cond`, `while.body`, `after.while`;
  phi в заголовке для переменных, мутирующих в теле.
* **Где и почему phi?** В точках слияния: после IF (переменная, присвоенная
  в обеих ветках), в заголовке while (перенос инвариантов/счётчиков).
  tinylang не использует alloca+mem2reg для локалов — поэтому phi обязаны
  строиться на лету; см. Braun et al. 2013, «Simple and Efficient
  Construction of SSA Form».

---

## 3. Реальные выводы (сдача = показать терминал)

### 3.1 Лаба 3

```
$ lli gcd.ll
gcd(12, 15) = 3
$ ./gcd; ./gcd_c
gcd(12, 15) = 3
gcd(12, 15) = 3
```

### 3.2 Лаба 4 — эмиссия IR всех 7 тестов (LLVM 24)

Команда:

```bash
TL=~/cmpl/lab4/tinylang/build/tools/driver/tinylang
cd ~/cmpl/lab4/lab/tests
for t in *.mod; do "$TL" --emit-llvm -o "${t%.mod}.ll" "$t"; done
```

Диагностики нет; получено 7 `.ll`. Подтверждения:

`boolean-phi.ll` (phi i1 в заголовке while; BOOLEAN→i1):

```
define i1 @_t7BoolPhi6Toggle(i64 %n) {
entry:
  br label %while.cond
while.cond:
  %0 = phi i1 [ %3, %while.body ], [ false, %entry ]
  %1 = phi i64 [ %4, %while.body ], [ %n, %entry ]
  %2 = icmp sgt i64 %1, 0
  br i1 %2, label %while.body, label %after.while
while.body:
  %3 = xor i1 %0, true
  %4 = sub nsw i64 %1, 1
  br label %while.cond
after.while:
  ret i1 %0
}
```

`boolean-global.ll` (глобальная BOOLEAN-переменная — теперь работает
благодаря фиксу `Mod`):

```
@_t10BoolGlobal4flag = private global i1
define void @_t10BoolGlobal3Set() {
entry:
  store i1 true, ptr @_t10BoolGlobal4flag, align 1
}
```

`boolean-expr.ll`: `icmp sgt/slt i64` → `and i1` / `or i1`, `ret i1`.
`boolean-param-ret.ll`: `define i1 @_t12BoolParamRet3Not(i1 %b)`,
`xor i1 %b, true`; `define i1 @_t12BoolParamRet6IsTrue(i64 %dummy)` с
`icmp eq i64 %dummy, 1`.
`boolean-var.ll`: `private global i1` + `load`/`store i1` + `br i1`.

`if-then-else.ll` — три новых блока (ответ из §2.4):

```
if.body:                                          ; preds = %entry
  ret i64 1
else.body:                                        ; preds = %entry
  ret i64 0
after.if:                                         ; No predecessors!
```

`while-blocks.ll` — три новых блока (предшественники — из комментариев IR):

```
while.cond:                                       ; preds = %while.body, %entry
  %0 = phi i64 [ %3, %while.body ], [ 0, %entry ]
  %1 = phi i64 [ %4, %while.body ], [ %n, %entry ]
while.body:                                       ; preds = %while.cond
  %3 = add nsw i64 %0, %1
  %4 = sub nsw i64 %1, 1
after.while:                                      ; preds = %while.cond
  ret i64 %0
```

(Полные `.ll` — в `cmpl/compilers-fall-lec4/lab4/LAB4.md`, приложение.)

---

## 4. Команды для воспроизведения с нуля

```bash
# лаба 3
cd ~/cmpl/lab3 && export PATH=$HOME/opt/clang/bin:$PATH
lli gcd.ll
clang gcd.ll -o gcd && ./gcd

# лаба 4 — чистая пересборка
cd ~/cmpl/lab4/tinylang
rm -rf build && mkdir -p build && cd build
cmake -G Ninja -DLLVM_DIR=$HOME/opt/clang/lib/cmake/llvm -DCMAKE_BUILD_TYPE=Release ..
ninja tinylang
TL=$PWD/tools/driver/tinylang
cd ~/cmpl/lab4/lab/tests
for t in *.mod; do "$TL" --emit-llvm -o "${t%.mod}.ll" "$t"; done
```

Если LLVM не в `~/opt/clang` — найдите `LLVMConfig.cmake`:
`find ~ /usr/lib -name LLVMConfig.cmake 2>/dev/null` и укажите его папку
в `-DLLVM_DIR`.

---

## 5. Что честно не сделано (не сочинять на сдаче)

* Вызовы процедур в кодогенераторе — `report_fatal_error("not implemented")`
  (сознательно, не входит в задание).
* Операторы на уровне самого `MODULE` не кодогенерируются — поэтому
  `boolean-var.mod` обёрнут в `Main()`.
* Проверки «переменная использована до присваивания» нет — предсуществующее
  ограничение SSA-карты.
* `after.if`/`after.while` после `ret` — мёртвые блоки, кодогенератор
  печатает их всегда («No predecessors!») — особенность реализации.
* `boolean-var.ll` содержит `store` + сразу `load` — оптимизаций нет
  (`--emit-llvm` печатает сырой IR).
* Лабы 1–2 здесь не разбираются (сделаны ранее на машине пользователя).

## 6. Где что лежит

| Что | Путь (на машине пользователя) | Путь (в репозитории) |
|-----|------------------------------|----------------------|
| gcd.c | `~/cmpl/lab3/gcd.c` | `cmpl/compilers-fall-lec3/gcd.c` |
| gcd.ll | `~/cmpl/lab3/gcd.ll` | `cmpl/compilers-fall-lec3/gcd.ll` |
| LAB3.md (отчёт 3) | — | `cmpl/compilers-fall-lec3/lab3/LAB3.md` |
| LAB4.md (отчёт 4, с приложением всех .ll) | — | `cmpl/compilers-fall-lec4/lab4/LAB4.md` |
| Кодогенератор | `~/cmpl/lab4/tinylang/lib/CodeGen/` | `cmpl/compilers-fall-lec4/tinylang/…` |
| Тесты лабы 4 | `~/cmpl/lab4/lab/tests/*.mod` | `cmpl/compilers-fall-lec4/lab/tests/` |
| Этот документ | — | `cmpl/LAB34-OTCHET.md` |

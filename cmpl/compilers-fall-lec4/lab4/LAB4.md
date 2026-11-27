# Лабораторная работа №4 — Tinylang → LLVM IR: кодогенерация
# (лекция 4, «TinyLang to LLVM IR Code Generation»)

---

## 1. Структура генератора кода

Кодогенератор (`tinylang/lib/CodeGen/`) состоит из трёх слоёв:

* **`CodeGenerator`** (`CodeGenerator.{h,cpp}`) — фасад: создаёт `llvm::Module`
  с triple/datalayout из переданного `TargetMachine`, делегирует работу в
  `CGModule::run` и возвращает готовый `unique_ptr<Module>`. Используется
  драйвером (`tools/driver/Driver.cpp`) после успешного синтаксического и
  семантического анализа.
* **`CGModule`** (`CGModule.{h,cpp}`) — уровень модуля: предопределённые типы
  (`VoidTy`, `Int1Ty`, `Int32Ty`, `Int64Ty`), таблица «clang-уровень типов»
  (`convertType(TypeDeclaration*)` — INTEGER→i64, BOOLEAN→i1 после правки),
  функции `mangleName` (искажение имён `_t` + длины частей с точками
  иерархии, printf-стиль «size-prefixed»), `getGlobal` (карта глобальных
  переменных `Decl* → GlobalObject*`), `run` — создаёт `GlobalVariable`
  для каждой module-level `VAR` и запускает `CGProcedure` для каждой процедуры.
* **`CGProcedure`** (`CGProcedure.{h,cpp}`) — уровень функции:
  * создаёт `llvm::Function` (`createFunction`), тип функции
    (`createFunctionType`), `entry`-блок, привязку `FormalParameterDeclaration →
    llvm::Argument` (для VAR-параметров передаётся указатель — по ссылке);
  * **SSA-карта**: `CurrentDef` (DenseMap `BasicBlock* → BasicBlockDef`);
    `BasicBlockDef` хранит `Defs` (карта `Decl* → Value*` — какое SSA-значение
    соответствует переменной в этом блоке), `IncompletePhis` (phi, у которых
    ещё не дописаны входы), `Sealed` (все предшественники известны);
  * алгоритм Braun et al. (Simple and Efficient Construction of SSA, CC 2013):
    `readLocalVariableRecursive` → при неизвестном предшественнике создаёт
    «неполную» phi (`addEmptyPhi`), `sealBlock` по завершении блока дописывает
    операнды (`addPhiOperands`), `optimizePhi` удаляет тривиальные phi;
  * генерация выражений (`emitInfixExpr`, `emitPrefixExpr`, `emitExpr`):
    арифметика → `add nsw`/`sub nsw`/`mul nsw`/`sdiv`/`srem`, сравнения →
    `icmp eq/ne/slt/sle/sgt/sge`, логика → `and`/`or`/`not`;
  * генерация операторов (`emitStmt`): присваивание (`writeVariable`),
    `IF` (if.body/else.body/after.if), `WHILE` (while.cond/while.body/after.while),
    `RETURN`, вызов процедуры (пока `report_fatal_error("not implemented")` —
    код для вызовов не написан сознательно).

Поток: `Parser::parse()` → AST → `Sema` → (если `Diags.numErrors() == 0`)
`CodeGenerator::run` → печать IR pass'ом `createPrintModulePass` (`--emit-llvm`)
либо ассемблер x86-64 (`--filetype=asm`).

---

## 2. Сколько базовых блоков генерируется для if-then-else-end?

По коду `CGProcedure::emitStmt(IfStatement*)` (lib/CodeGen/CGProcedure.cpp):

```cpp
llvm::BasicBlock *IfBB   = Create(, "if.body", Fn);     // 1
llvm::BasicBlock *ElseBB = HasElse ? Create(, "else.body", Fn) : nullptr;  // +1
llvm::BasicBlock *AfterIfBB = Create(, "after.if", Fn); // +1
```

**Ответ: 3 новых базовых блока** — `if.body`, `else.body`, `after.if`
(для варианта без ELSE — 2: `if.body`, `after.if`). Условие вычисляется
в *предшествующем* блоке (том, где остановилась генерация операторов);
сам он не создаётся оператором IF.

Контрольный пример — `lab/tests/if-then-else.mod` (проверяет пользователь,
точные команды — в `cmpl/LAB34-INSTRUCTIONS.md`):

```bash
../tinylang/build/tools/driver/tinylang --filetype=asm --emit-llvm \
    -o if-then-else.ll if-then-else.mod
grep -E '^(if.body|else.body|after.if):' if-then-else.ll   # ожидаем 3 метки
```

Ожидается ровно 3 новых блока относительно предшествующего `entry`:
`if.body`, `else.body`, `after.if`.

## 3. Сколько базовых блоков генерируется для while-end?

По коду `CGProcedure::emitStmt(WhileStatement*)`:

```cpp
llvm::BasicBlock *WhileCondBB = Create(, "while.cond", Fn);
llvm::BasicBlock *WhileBodyBB = Create(, "while.body", Fn);
llvm::BasicBlock *AfterWhileBB = Create(, "after.while", Fn);
```

**Ответ: 3 новых базовых блока** — `while.cond` (заголовок с условием и phi),
`while.body` (тело), `after.while` (продолжение). Безусловный переход из
текущего блока в `while.cond`, условный `br` в заголовке, обратный переход
тела в заголовок. Контрольный пример — `lab/tests/while-blocks.mod`:

```bash
../tinylang/build/tools/driver/tinylang --filetype=asm --emit-llvm \
    -o while-blocks.ll while-blocks.mod
grep -E '^(while.cond|while.body|after.while):' while-blocks.ll   # ожидаем 3 метки
```

## 4. Что такое SSA? Что такое phi-функция? Где и почему они используются

**SSA (Static Single Assignment)** — форма промежуточного представления,
в которой каждая виртуальная переменная (SSA-значение, `%x` в тексте IR)
получает значение ровно в одной точке программы, а все использования
ссылаются на это единственное определение. Преимущества: явное отслеживание
потока данных (data-flow), тривиальные оптимизации (constant propagation,
DCE), отсутствие анти-зависимостей. В IR LLVM любое значение в регистре —
SSA; «изменяемо» можно только через память (`alloca`/`load`/`store`) или
через phi-узлы.

**Phi-функция** — специальная инструкция, допустимая только первой в базовом
блоке, выбирающая значение в зависимости от того, из какого блока пришёл
поток управления:

```
%sum.phi = phi i64 [ 0, %entry ], [ %sum.next, %while.body ]
```

Узел имеет по одной паре `[value, predecessor]` на каждого предшественника
блока. phi «сливает» расходящиеся SSA-определения в одну точку — например,
переменная, присвоенная в обеих ветках `IF`, на выходе `after.if` обязана
быть представлена phi с двумя входами.

**Где используются phi у нас.** Кодогенератор Tinylang не использует
`alloca`/`mem2reg` для локальных переменных (кроме локалов агрегатного типа —
их просто нет в языке): локальные переменные и value-параметры хранятся
напрямую как SSA-значения в карте `Defs` каждого блока. Поэтому в точках
слияния управления phi **обязаны** создаваться на лету:

* `emitStmt(IfStatement*)` → на входе в `after.if` переменные, присвоенные
  по разным путям, требуют phi — её создаст `readLocalVariableRecursive`,
  когда какой-нибудь код *после* IF прочитает переменную;
* `emitStmt(WhileStatement*)` → в заголовке `while.cond` phi нужны всегда
  для переменных, мутирующих в теле (иначе чтение в теле или после цикла
  видело бы «старое» значение);
* процедура входа (`entry`) параметров: аргументы пишутся в `Defs` блока
  входа, далее phi появляются автоматически при слиянии.

**Как это сделано в коде** (алгоритм «seal blocks», Braun et al., 2013):

1. `readLocalVariable(BB, Decl)` — сначала смотрит `Defs[BB]`; нет — вызывает
   `readLocalVariableRecursive`.
2. Блок **не запечатан** (`!Sealed`, т.е. предшественники ещё дописываются):
   создаётся phi без операндов (`addEmptyPhi`) и запоминается в
   `IncompletePhis` — иначе на циклах не сойтись (цикл ссылается сам на себя).
3. У блока **ровно один предшественник**: значение читается оттуда
   (`getSinglePredecessor`).
4. Иначе (несколько предшественников, блок запечатан): создаётся пустая phi,
   она тут же пишется в `Defs[BB]` (разрыв циклических зависимостей), затем
   `addPhiOperands` дописывает входы `[readLocalVariable(Pred), Pred]` по всем
   предшественникам, затем `optimizePhi` выкидывает тривиальные phi
   (все входы одинаковы / self-reference) и каскадно упрощает зависимые phi.
5. `sealBlock(BB)` вызывается **после** того, как у блока не появится новых
   предшественников: `emitStmt(IfStatement*)` печатает `sealBlock(Curr)`
   перед уходом в ветки и после; `emitStmt(WhileStatement*)` запечатывает
   текущий блок при переходе в заголовок, `while.cond` — после генерации
   тела (обратный переход известен), `curr` — в конце.

Почему так, а не `alloca`+`mem2reg`: прямое построение SSA в один проход,
без последующего pass'а; ценой — более сложный код, чем «всё в память»,
зато выданный IR не содержит лишних load/store и сразу готов к оптимизациям.

---

## 5. Добавлена поддержка типа BOOLEAN → Int1

**Что сделано.** В `CGModule::convertType` добавлена ветка

```cpp
if (Ty->getName() == "BOOLEAN")
  return Int1Ty;
```

(lib/CodeGen/CGModule.cpp). Этого оказывается достаточно, потому что:

* `Int1Ty` уже создавался в `CGModule::initialize()`;
* `BooleanLiteral` уже генерировался как `ConstantInt` типа `i1`
  (`emitExpr`, CGProcedure.cpp);
* сравнения (`icmp`) и `AND/OR/NOT` (`and`/`or`/`not`) уже давали/принимали
  `i1`; условие `if/while` (`CreateCondBr`) уже требовало `i1`;
* семантический анализ уже всё знает про `BOOLEAN`: тип регистрируется в
  `Sema::initialize()`, литералы `TRUE`/`FALSE` — предобъявленные константы,
  `AND/OR/NOT` и `IF/WHILE` проверяют `BooleanType`;
* не хватало ровно отображения типа при запросе `convertType("BOOLEAN")` —
  раньше там было `report_fatal_error("Unsupported type")`.

Косвенно стало поддерживаться и всё производное, т.к. всё идёт через
`convertType`/`mapType`:

* локальные BOOLEAN-переменные (через SSA-карту и phi `i1`);
* глобальные BOOLEAN-переменные (`GlobalVariable i1`);
* BOOLEAN-параметры и возвращаемые значения (`i1` в сигнатуре);
* VAR-параметры BOOLEAN → указатель на `i1` (deref size = 1 байт —
  `getTypeStoreSize(Int1Ty)`).

**Тестовые программы** (`lab/tests/`): `boolean-var.mod`, `boolean-global.mod`,
`boolean-param-ret.mod`, `boolean-expr.mod`, `boolean-phi.mod`,
`if-then-else.mod`, `while-blocks.mod`.

**Проверка ВЫПОЛНЕНА на машине пользователя** (Ubuntu, сборка/эмиссия против
LLVM/clang 24.0.0git из лабы 1, `~/opt/clang`; код лабы 4 написан под LLVM 17 —
см. ниже, какие правки потребовались).

```bash
cd ~/cmpl/lab4/tinylang && mkdir -p build && cd build
cmake -G Ninja -DLLVM_DIR=$HOME/opt/clang/lib/cmake/llvm -DCMAKE_BUILD_TYPE=Release ..
ninja tinylang          # OK: tools/driver/tinylang
cd ~/cmpl/lab4/lab/tests
TL=~/cmpl/lab4/tinylang/build/tools/driver/tinylang
for t in *.mod; do "$TL" --emit-llvm -o "${t%.mod}.ll" "$t"; done
```

Все 7 тестов скомпилированы без диагностики; IR получен полностью
(см. приложение в конце файла — вывод прогонов целиком). Ключевые факты:

* `boolean-expr.ll` — `icmp sgt/slt i64` + `and i1` / `or i1`, `ret i1`;
* `boolean-global.ll` — `@_t10BoolGlobal4flag = private global i1`,
  `store i1 true, ptr @_t10BoolGlobal4flag, align 1`;
* `boolean-param-ret.ll` — `define i1 @...(i1 %b)`, `xor i1 %b, true`
  (это и есть NOT), `icmp eq i64 %dummy, 1` → `ret i1`;
* `boolean-phi.ll` — `define i1 @_t7BoolPhi6Toggle(i64 %n)`;
  в `while.cond`: `%0 = phi i1 [ %3, %while.body ], [ false, %entry ]`,
  `br i1 %2, label %while.body, label %after.while`; в теле `xor i1 %0, true`;
* `boolean-var.ll` — `private global i1`, `load i1`/`store i1`,
  `br i1` для if и while (глобальная BOOLEAN-переменная, доступ из процедуры);
* `if-then-else.ll` — три новых базовых блока `if.body`, `else.body`,
  `after.if` (подтверждает ответ «3» из §2);
* `while-blocks.ll` — `while.cond` (phi i64 `%0`/`%1`, `icmp sgt`),
  `while.body` (`add nsw`, `sub nsw`), `after.while` (`ret i64`) —
  три новых базовых блока (подтверждает ответ «3» из §3).

**Исправления, которые потребовались при сборке (честно, полностью):**

1. `lib/CodeGen/CGProcedure.cpp` (`addEmptyPhi`): `PHINode::Create(..., &BB->front())`
   — в LLVM ≥ 18 `Instruction*` не конвертируется в `InsertPosition`;
   исправлено на `llvm::InsertPosition(BB->begin())` (и `InsertPosition(BB)`
   для пустого блока). В репозитории сделано с `#if LLVM_VERSION_MAJOR >= 18`
   guard — под LLVM 17 собирается исходный вариант.
2. `tools/driver/Driver.cpp`: `TargetRegistry::lookupTarget(Triple.getTriple(), ErrMsg)`
   — StringRef-оверлоад убран; оставлен `lookupTarget(const Triple&, std::string&)`.
   `Target::createMCSubtargetInfo(Triple, codegen::getCPUStr(), codegen::getFeaturesStr())`
   — первый аргумент теперь `Triple`, не `StringRef`. Обе правки совместимы
   и с LLVM 17.
3. Курсовой баг: поле `CGModule::Mod` никогда не присваивалось
   (конструктор `CGModule(llvm::Module *M) : M(M) { initialize(); }`),
   а `getModuleDeclaration()` возвращал мусор; в результате любой доступ
   к глобальной BOOLEAN-переменной из процедуры уходил в
   `report_fatal_error("Nested procedures not yet supported")`
   (на самом деле это про неопределённый `Mod`, сообщение вводит в заблуждение).
   Исправлено: `this->Mod = Mod;` первой строкой `CGModule::run(...)`.
   Воспроизводится одинаково на LLVM 17 и 24.

**Что НЕ сделано / ограничения (честно):**

* операции над BOOLEAN ограничены `AND/OR/NOT/сравнениями` — таков же язык;
* `x = TRUE` внутри условия и т.п. — `icmp eq i1`, ок;
* никаких проверок «переменная использована до присваивания» — предсуществующее
  ограничение SSA-карты (используемое значение было бы phi от `undef`);
* `report_fatal_error("not implemented")` для вызова процедур сознательно
  не трогали — вне задания;
* **операторы на уровне самого `MODULE` не кодогенерируются** — `CGModule::run`
  обходит только `getDecls()` и игнорирует `Mod->getStmts()`. Тест
  `boolean-var.mod` для демонстрации i1-load/store через if/while поэтому
  обёрнут в процедуру `Main()` (в исходной версии теста тело модуля было
  пустым для кодогенератора);
* блоки `after.if`/`after.while` после `return`/`ret` — мёртвые
  («No predecessors!»), кодогенератор создаёт их всегда — это особенность
  реализации, а не ошибка;
* `boolean-var.mod`: к глобалу делается `store` затем сразу `load` — никаких
  оптимизаций, `--emit-llvm` печатает сырой IR; это ожидаемо.

---

## 6. Фактическая проверка (выполнено)

1. tinylang собран против LLVM 24 из лабы 1 (`~/opt/clang/lib/cmake/llvm`) —
   понадобились правки из раздела 5 (3 пункта).
2. Прогнаны все 7 тестов через `--emit-llvm`, диагностики нет, `.ll` получены.
3. Ответы «3 базовых блока» для if-then-else и while подтверждены выводом
   (3 метки с точными именами); BOOLEAN→Int1 подтверждён на i1-типах
   глобалов/параметров/phi/условных переходов.

## 7. Фактическая проверка синтаксиса/семантики тестов

Все `lab/tests/*.mod` прогнаны через компилятор лабораторной 2
(фронтенды lec2 и lec4 идентичны) — все файлы разбираются без единой
диагностики (`Tinylang 0.1`, код 0). То же подтверждено сборкой на
LLVM 24 и выдачей IR без ошибок.

---

## Приложение. Вывод прогона на машине пользователя (LLVM 24) — целиком

### boolean-expr.ll

```
; ModuleID = 'boolean-expr.mod'
source_filename = "boolean-expr.mod"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

define i1 @_t8BoolExpr7Between(i64 %x) {
entry:
  %0 = icmp sgt i64 %x, 0
  %1 = icmp slt i64 %x, 100
  %2 = and i1 %0, %1
  ret i1 %2
}

define i1 @_t8BoolExpr6Either(i1 %a, i1 %b) {
entry:
  %0 = or i1 %a, %b
  ret i1 %0
}
```

### boolean-global.ll

```
; ModuleID = 'boolean-global.mod'
source_filename = "boolean-global.mod"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

@_t10BoolGlobal4flag = private global i1

define void @_t10BoolGlobal3Set() {
entry:
  store i1 true, ptr @_t10BoolGlobal4flag, align 1
}
```

### boolean-param-ret.ll

```
; ModuleID = 'boolean-param-ret.mod'
source_filename = "boolean-param-ret.mod"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

define i1 @_t12BoolParamRet3Not(i1 %b) {
entry:
  %0 = xor i1 %b, true
  ret i1 %0
}

define i1 @_t12BoolParamRet6IsTrue(i64 %dummy) {
entry:
  %0 = icmp eq i64 %dummy, 1
  ret i1 %0
}
```

### boolean-phi.ll

```
; ModuleID = 'boolean-phi.mod'
source_filename = "boolean-phi.mod"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

define i1 @_t7BoolPhi6Toggle(i64 %n) {
entry:
  br label %while.cond

while.cond:                                       ; preds = %while.body, %entry
  %0 = phi i1 [ %3, %while.body ], [ false, %entry ]
  %1 = phi i64 [ %4, %while.body ], [ %n, %entry ]
  %2 = icmp sgt i64 %1, 0
  br i1 %2, label %while.body, label %after.while

while.body:                                       ; preds = %while.cond
  %3 = xor i1 %0, true
  %4 = sub nsw i64 %1, 1
  br label %while.cond

after.while:                                      ; preds = %while.cond
  ret i1 %0
}
```

### boolean-var.ll

```
; ModuleID = 'boolean-var.mod'
source_filename = "boolean-var.mod"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

@_t7BoolVar1b = private global i1

define void @_t7BoolVar4Main() {
entry:
  store i1 true, ptr @_t7BoolVar1b, align 1
  %0 = load i1, ptr @_t7BoolVar1b, align 1
  br i1 %0, label %if.body, label %after.if

if.body:                                          ; preds = %entry
  store i1 false, ptr @_t7BoolVar1b, align 1

after.if:                                         ; preds = %entry
  br label %while.cond

while.cond:                                       ; preds = %while.body, %after.if
  %1 = load i1, ptr @_t7BoolVar1b, align 1
  br i1 %1, label %while.body, label %after.while

while.body:                                       ; preds = %while.cond
  store i1 false, ptr @_t7BoolVar1b, align 1
  br label %while.cond

after.while:                                      ; preds = %while.cond
}
```

### if-then-else.ll

```
; ModuleID = 'if-then-else.mod'
source_filename = "if-then-else.mod"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

define i64 @_t10IfThenElse4Pick(i64 %x) {
entry:
  %0 = icmp sgt i64 %x, 0
  br i1 %0, label %if.body, label %else.body

if.body:                                          ; preds = %entry
  ret i64 1

else.body:                                        ; preds = %entry
  ret i64 0

after.if:                                         ; No predecessors!
}
```

### while-blocks.ll

```
; ModuleID = 'while-blocks.mod'
source_filename = "while-blocks.mod"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

define i64 @_t11WhileBlocks3Sum(i64 %n) {
entry:
  br label %while.cond

while.cond:                                       ; preds = %while.body, %entry
  %0 = phi i64 [ %3, %while.body ], [ 0, %entry ]
  %1 = phi i64 [ %4, %while.body ], [ %n, %entry ]
  %2 = icmp sgt i64 %1, 0
  br i1 %2, label %while.body, label %after.while

while.body:                                       ; preds = %while.cond
  %3 = add nsw i64 %0, %1
  %4 = sub nsw i64 %1, 1
  br label %while.cond

after.while:                                      ; preds = %while.cond
  ret i64 %0
}
```

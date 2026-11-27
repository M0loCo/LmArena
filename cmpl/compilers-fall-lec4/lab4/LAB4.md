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
`boolean-param-ret.mod`, `boolean-expr.mod`, `boolean-phi.mod`.

Проверка (выполняет пользователь, LLVM 17 собранный в лабе 1):

```bash
cd cmpl/compilers-fall-lec4/lab/tests
for m in boolean-var boolean-global boolean-param-ret boolean-expr boolean-phi; do
  ../tinylang/build/tools/driver/tinylang --filetype=asm --emit-llvm \
     -o $m.ll $m.mod
done
grep -E 'i1' boolean-phi.ll
```

Ожидаемое: `define i1 @_t...`, `phi i1` (в `while.cond` для boolean-phi.mod),
`store i1`, `load i1`, `br i1`, `and i1`/`or i1`/`xor i1` (для NOT: `xor i1 %a, true`),
`icmp eq i1`. Полные .ll — приложить в отчёт (`lab4/boolean-*.ll`) или показать
на защите.

**Что НЕ сделано / ограничения (честно):**

* операции над BOOLEAN ограничены `AND/OR/NOT/сравнениями` — таков же язык;
* `x = TRUE` внутри условия и т.п. — `icmp eq i1`, ок;
* никаких проверок «переменная использована до присваивания» — предсуществующее
  ограничение SSA-карты (используемое значение было бы phi от `undef`);
* `report_fatal_error("not implemented")` для вызова процедур сознательно
  не трогали — вне задания.

---

## 6. Что делает пользователь (чек-лист)

1. Собрать tinylang из `compilers-fall-lec4/tinylang` против своего LLVM
   (см. `cmpl/LAB34-INSTRUCTIONS.md`, шаг 4).
2. Прогнать тесты из `lab/tests` через `--emit-llvm`.
3. Приложить полученные `if-then-else.ll`, `while-blocks.ll`,
   `boolean-*.ll` в этот каталог (или показать на защите) — они служат
   доказательством подсчёта блоков и отображения BOOLEAN→Int1.

## 7. Фактическая проверка синтаксиса/семантики тестов

Все `lab/tests/*.mod` прогнаны через компилятор лабораторной 2
(фронтенды lec2 и lec4 идентичны) — все файлы разбираются без
единой диагностики (`Tinylang 0.1`, код 0). Это гарантирует, что
дальнейшая генерация IR не упадёт по синтаксису; сама эмиссия IR
выполняется против LLVM пользователя (см. LAB34-INSTRUCTIONS.md).

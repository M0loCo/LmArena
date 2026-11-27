# Лабораторная работа №2 — Tinylang: фронтенд компилятора
# (лекция 2, «Диалект языка Modula-2»)

## 0. Сборка и запуск

```bash
mkdir -p /opt/build/tinylang2
cmake -S tinylang -B /opt/build/tinylang2 -G Ninja \
      -DLLVM_DIR=<сборка LLVM>/build/lib/cmake/llvm \
      -DCMAKE_BUILD_TYPE=Release
ninja -C /opt/build/tinylang2 tinylang
/opt/build/tinylang2/tools/driver/tinylang tinylang/example/Gcd.mod
```

(CMakeLists чуть поправлен для LLVM 17: `include_directories(${LLVM_INCLUDE_DIRS})`
вместо `${LLVM_INCLUDE_DIR}` — иначе при сборке против build-дерева LLVM
не находятся исходные заголовки; при установленном LLVM поведение прежнее.)

Собранный драйвер печатает баннер версии (и пофайлово разбирает аргументы):

```
$ /opt/build/tinylang2/tools/driver/tinylang tinylang/example/Gcd.mod
Tinylang 0.1
```

Пример `example/Gcd.mod` разбирается без единой диагностики (код 0).
Полный лог всех запусков — `lab2/run-output.log`.

Все тестовые программы лежат в `lab/tests/*.mod`. Вывод компилятора на каждую
приведён ниже; «ошибки» в них — ожидаемое поведение компилятора, являющееся
предметом изучения в этой работе.

---

## 1. Проверки типов данных

### 1.1 Сложение числа и строки

Файл: `lab/tests/add-number-and-string.mod`

```modula2
MODULE AddNumberAndString;
VAR y: INTEGER;
BEGIN
  y := 1 + "2";
END AddNumberAndString.
```

Результат запуска:

```
$ ./tools/driver/tinylang ../lab/tests/add-number-and-string.mod
Tinylang 0.1
```

Компилятор молча принимает программу. Поясним, почему.

1. Строки в языке **есть только на уровне лексера**: `lexer` умеет токен
   `string_literal` (см. `Lexer::string()`, lib/Lexer/Lexer.cpp), и токен
   `string_literal` встречается в `TokenKinds.def`.
2. В грамматике (файл `lib/Parser/tinylang.g`) и в рекурсивно-спускном
   парсере (`Parser::parseFactor`) **строкового литерала как единицы выражения
   нет**: `factor : integer_literal | "(" expression ")" | "NOT" factor | qualident ...`.
3. Поэтому `"2"` не распознаётся как factor; ветка `else { /*ERROR*/ }`
   в `parseFactor` вызывает `skipUntil(...)`, который **не печатает
   диагностику**, а молча пропускает токены до точки восстановления
   (`;`, `END` и др.). В итоге `parseTerm` возвращает `Right == nullptr`,
   `Sema::actOnSimpleExpression(Left=1, Right=nullptr, Op='+')`
   выполняется по ветке `if (!Right) return Left;` — и программа `y := 1 + "2"`
   вырождается в `y := 1`.

Это дефект учебного компилятора: некорректный ввод не приводится даже к
синтаксической ошибке — неподдерживаемый операнд «срезается» без диагностики.
Правильным поведением было бы сообщение `expected ... but found "2"` (как это
делает `expect()` в `Parser.h`) или отдельная ошибка о том, что строки как
тип данных в языке отсутствуют (тип `STRING` не реализован: в `Sema::initialize()`
регистрируются только `INTEGER` и `BOOLEAN`).

### 1.2 Сложение числа и логического значения (проверка типов выражений)

Файл: `lab/tests/add-int-bool.mod`

```modula2
MODULE AddIntBool;
VAR y: INTEGER;
BEGIN
  y := 1 + TRUE;
END AddIntBool.
```

Результат запуска (фактический):

```
$ tinylang lab/tests/add-int-bool.mod
lab/tests/add-int-bool.mod:5:10: error: types not compatible for operator +
  y := 1 + TRUE;
         ^
Tinylang 0.1
```

Сообщение формируется в `Sema::actOnSimpleExpression`
(lib/Sema/Sema.cpp, строки ~281–310): сравниваются `Left->getType()` и
`Right->getType()` (не равные указатели на синглтоны `IntegerType`/`BooleanType`),
далее `err_types_for_operator_not_compatible` с `tok::getPunctuatorSpelling(Op.getKind())`,
т.е. `+`. Диагностика печатается в stderr с подсветкой строки (SourceMgr).

**Как семантический анализатор хранит и анализирует информацию о типе выражений.**

* Каждое выражение — узел иерархии `Expr` (include/tinylang/AST/AST.h) с
  полем `TypeDeclaration *Ty`. Базовый класс `Expr` (строки ~211–240 AST.h)
  хранит `Kind`, `Ty`, `IsConstant`; тип задаётся конструктором и может быть
  прочитан/изменён через `getType()/setType()`.
* Литералы несут типы-«синглтоны»: `actOnIntegerLiteral` возвращает
  `IntegerLiteral` с `Ty = IntegerType`; TRUE/FALSE — `BooleanLiteral`
  с `Ty = BooleanType` (см. `Sema::initialize`).
* Доступ к переменной/константе/параметру берёт тип из объявления:
  `VariableAccess(VariableDeclaration *Var) : Expr(EK_Var, Var->getType(), ...)`
  и аналогично для параметра; тип константы берётся из её выражения
  (`ConstantAccess : Expr(EK_Const, Const->getExpr()->getType(), ...)`).
* Типы в компиляторе — **синглтоны**: `IntegerType` и `BooleanType` создаются
  один раз в `Sema::initialize()` и далее сравниваются **по указателю**
  (`Left->getType() != Right->getType()`, `Ty == IntegerType`). Никаких
  структурных сравнений, подтипов и неявных преобразований нет.
* Проверки:
  * `actOnExpression` (сравнения `= # < <= > >=`, строки ~262–280):
    сравнивает типы операндов, результат всегда `BOOLEAN`;
  * `actOnSimpleExpression` (`+ - OR`, строки ~281–310): тот же тест типа,
    результат `BOOLEAN` для `OR`, для `+ -` — тип операнда; константная
    свёртка `TRUE OR FALSE` и т.п.;
  * `actOnTerm` (`* / DIV MOD AND`, строки ~312–345): дополнительно
    проверяет `isOperatorForType(Op, Ty)` — арифметике нужен `INTEGER`,
    логике `AND/OR/NOT` нужен `BOOLEAN`;
  * присваивание (`actOnAssignment`, строки ~203–227): `Var->getType() != E->getType()`
    → `err_types_for_operator_not_compatible` с оператором `:=`;
  * параметры (`checkFormalAndActualParameters`, строки ~39–60): почленно
    сравнивает `F->getType() != Arg->getType()`.
* Вывод о диагностике: несовместимость типов арифметических операций
  обнаруживается именно в `actOnSimpleExpression`/`actOnTerm` через сравнение
  указателей на синглтоны типов; сообщение — `err_types_for_operator_not_compatible`.
* Отдельно: операция `slash` для `INTEGER` не разрешена
  (`isOperatorForType`: `case tok::slash: return false; // REAL not implemented`),
  т.е. `a := 1 / 2` тоже даст ошибку — вещественная арифметика не реализована.

### 1.3 WHILE с условием типа INTEGER

Файл: `lab/tests/while-int-condition.mod`

```modula2
MODULE WhileIntCondition;
VAR x: INTEGER;
BEGIN
  x := 10;
  WHILE x DO
    x := x - 1;
  END;
END WhileIntCondition.
```

Результат запуска (фактический):

```
$ tinylang lab/tests/while-int-condition.mod
lab/tests/while-int-condition.mod:6:3: error: expression of IF statement must have type BOOLEAN
  WHILE x DO
  ^
Tinylang 0.1
```

Ошибку выдаёт `Sema::actOnWhileStatement` (lib/Sema/Sema.cpp, строки ~235–246):
сравнивает `Cond->getType() != BooleanType` и репортит `err_while_expr_must_be_bool`.
**Замечание (дефект диагностики):** текст сообщения зашит как
«expression of IF statement must have type BOOLEAN» — опечатка автора исходника,
`Diagnostic.def` строка 27; ID д-иагностики при этом отдельный
(`err_while_expr_must_be_bool`), так что по ID сообщение отличается от IF-версии,
а по тексту — нет. IF с целочисленным условием ловится симметрично
(`actOnIfStatement`, `err_if_expr_must_be_bool`), см. `lab/tests/if-int-condition.mod`.

### 1.4 Где регистрируются типы данных INTEGER, BOOLEAN?

В `Sema::initialize()` — lib/Sema/Sema.cpp, строки 62–88:

```cpp
void Sema::initialize() {
  // Setup global scope.
  CurrentScope = new Scope();          // глобальная область видимости
  CurrentDecl = nullptr;
  IntegerType = new TypeDeclaration(CurrentDecl, SMLoc(), "INTEGER");
  BooleanType = new TypeDeclaration(CurrentDecl, SMLoc(), "BOOLEAN");
  TrueLiteral = new BooleanLiteral(true, BooleanType);
  FalseLiteral = new BooleanLiteral(false, BooleanType);
  TrueConst = new ConstantDeclaration(CurrentDecl, SMLoc(), "TRUE", TrueLiteral);
  FalseConst = new ConstantDeclaration(CurrentDecl, SMLoc(), "FALSE", FalseLiteral);
  CurrentScope->insert(IntegerType);
  CurrentScope->insert(BooleanType);
  CurrentScope->insert(TrueConst);
  CurrentScope->insert(FalseConst);
}
```

`Sema` конструируется в драйвере на каждый файл (`Driver.cpp`: `auto TheSema = Sema(Diags);`),
поэтому регистрация происходит один раз до разбора программы. Оба типа вставляются
в **глобальную область** (`Scope` с `Parent == nullptr`) как `TypeDeclaration`,
TRUE/FALSE — как `ConstantDeclaration`. Искать их потом можно через
`Scope::lookup` по имени ("INTEGER", "BOOLEAN", "TRUE", "FALSE").

---

## 2. Проверки контекста использования языковых конструкций

### 2.1 RETURN 10 в процедуре

Файл: `lab/tests/return-10-in-procedure.mod`

```modula2
MODULE Return10InProcedure;
PROCEDURE P();
BEGIN
  RETURN 10;
END P;
BEGIN
  P();
END Return10InProcedure.
```

Результат запуска (фактический):

```
$ tinylang lab/tests/return-10-in-procedure.mod
lab/tests/return-10-in-procedure.mod:5:3: error: Procedure does not allow RETURN with value
  RETURN 10;
  ^
Tinylang 0.1
```

**Как и где выполняется проверка.**

1. Синтаксис: `Parser::parseStatement` видит `RETURN` → `parseReturnStatement`
   (lib/Parser/Parser.cpp, строки ~382–400): считывает необязательное выражение
   (`tok::integer_literal` входит в набор допустимых стартовых токенов) и
   вызывает `Actions.actOnReturnStatement(Stmts, Loc, E)`.
2. Лексически/синтаксически `RETURN 10` в процедуре допустим — грамматика не
   различает процедуры и функции, деление — семантическое.
3. Семантика: `Sema::actOnReturnStatement` (lib/Sema/Sema.cpp, строки ~247–260)
   восстанавливает текущую процедуру из `CurrentDecl`
   (`cast<ProcedureDeclaration>(CurrentDecl)` — именно поэтому `CurrentDecl`
   обновляется при входе/выходе из области через `EnterDeclScope`),
   и различает три случая:

   | RetType проф. | RetVal | Результат |
   |---|---|---|
   | есть | нет | `err_function_requires_return` («Function requires RETURN with value») |
   | нет  | есть | `err_procedure_requires_empty_return` («Procedure does not allow RETURN with value») |
   | есть | есть | сравнение `Proc->getRetType() != RetVal->getType()` → `err_function_and_return_type` |

   Для `PROCEDURE P()` возвращаемого типа нет (`getRetType() == nullptr`),
   `RetVal` задан ⇒ срабатывает вторая ветка.
4. Дополнительно корректность использования `RETURN` в функции проверяется
   через `actOnProcedureHeading` / `actOnProcedureDeclaration`: имя после `END`
   должно совпадать с именем процедуры (`err_proc_identifier_not_equal`),
   DECLARE о возвращаемом типе проверяется в `actOnProcedureHeading`
   (RETURN TYPE должен быть типом, иначе `err_returntype_must_be_type`).

Контрольный положительный случай — `return10-type-ok.mod`:
`PROCEDURE Two() : INTEGER; RETURN 10;` — компилируется без ошибок.

---

## 3. Области видимости (scope)

### 3.1 Две переменные с одинаковыми именами в разных областях

Файл: `lab/tests/scope-shadow.mod`

```modula2
MODULE ScopeShadow;
VAR x: INTEGER;
PROCEDURE Shadow();
VAR x: INTEGER;
BEGIN
  x := 1;          (* локальная x *)
END Shadow;
BEGIN
  x := 42;         (* глобальная x *)
  Shadow();
END ScopeShadow.
```

Результат запуска: `Tinylang 0.1` — без единой диагностики. Тенью (shadowing)
перекрытие имени разрешено: `Scope::insert` помещает объявление в **текущую**
область, одноимённые сущности в разных областях друг другу не мешают.

### 3.2 Как осуществляется поиск имени (scope → parent)

`lib/Sema/Scope.cpp` (строки 13–22, полный листинг):

```cpp
Decl *Scope::lookup(StringRef Name) {
  Scope *S = this;
  while (S) {
    StringMap<Decl *>::const_iterator I =
        S->Symbols.find(Name);
    if (I != S->Symbols.end())
      return I->second;
    S = S->getParent();
  }
  return nullptr;
}
```

Механика целиком:

* Каждый `Scope` хранит `Scope *Parent` и `StringMap<Decl *> Symbols`
  (include/tinylang/Sema/Scope.h) — хэш-таблицу «имя → объявление».
* В точке любого поиска вызов идёт от `CurrentScope`
  (`Sema::actOnQualIdentPart`, lib/Sema/Sema.cpp: `if (Decl *D = CurrentScope->lookup(Name))`),
  т.е. поиск идёт от внутренней области к самой внешней:
  локаль → параметры процедуры → модуль → глобальная область (где лежат
  INTEGER/BOOLEAN/TRUE/FALSE). Первое совпадение выигрывает — это и есть
  правильная семантика перекрытия (теней).
* Связывание областей делает `Sema::enterScope` (`CurrentScope = new Scope(CurrentScope)`),
  отсоединение — `leaveScope` (`Scope *Parent = CurrentScope->getParent(); delete CurrentScope; CurrentScope = Parent;`),
  причём `leaveScope` также восстанавливает `CurrentDecl = CurrentDecl->getEnclosingDecl()`,
  чтобы `actOnReturnStatement` снова видел внешнюю процедуру.
* RAII-обёртка `EnterDeclScope` (Sema.h, строки ~94–105) гарантирует
  вход/выход даже при ошибочном разборе; используется в `parseCompilationUnit`
  (модуль) и `parseProcedureDeclaration` (процедура) — lib/Parser/Parser.cpp:
  строки 32 и 184.
* Поэтому в 3.1: внутри `Shadow` обращение к `x` находится в локальной области
  процедуры, снаружи — в области модуля; одно и то же имя, два разных `Decl*`.

Квалифицированные имена (`Module.Name`) ищутся по-другому — через
`actOnQualIdentPart` веткой `dyn_cast<ModuleDeclaration>(Prev)` с перебором
`getDecls()` модуля (импорт модулей не реализован — `err_not_yet_implemented`).

### 3.3 Функция с одинаковыми именами формальных параметров

Файл: `lab/tests/duplicate-function-params.mod`

```modula2
MODULE DuplicateFunctionParams;
PROCEDURE F(a, a: INTEGER) : INTEGER;
BEGIN
  RETURN a;
END F;
VAR y: INTEGER;
BEGIN
  y := F(1, 2);
END DuplicateFunctionParams.
```

Результат запуска (фактический):

```
$ tinylang lab/tests/duplicate-function-params.mod
lab/tests/duplicate-function-params.mod:3:16: error: symbol a already declared
PROCEDURE F(a, a: INTEGER) : INTEGER;
               ^
lab/tests/duplicate-function-params.mod:3:11: error: wrong number of parameters
PROCEDURE F(a, a: INTEGER) : INTEGER;
          ^
Tinylang 0.1
```

Вторая диагностика — закономерное следствие первой: отклонённый дубликат
`a` в `FormalParamList` не попадает (`actOnFormalParameterDeclaration` не
делает `Params.push_back` для не прошедшей вставки), поэтому при вызове
`F(1, 2)` число фактических параметров (2) не совпадает с числом формальных (1).

**Как хранятся имена параметров.** Список идентификаторов считывается
`Parser::parseIdentList` (lib/Parser/Parser.cpp, строки ~676–693) в
`IdentList = std::vector<std::pair<SMLoc, StringRef>>` — пара «позиция + имя»,
без разрешения имён. Для каждой пары `Sema::actOnFormalParameterDeclaration`
(lib/Sema/Sema.cpp, строки ~131–155) создаёт `FormalParameterDeclaration`
(имя сохраняется в поле `Decl::Name`, тип — `Decl*` на `TypeDeclaration`,
флаг `IsVar`) и делает `CurrentScope->insert(Decl)`. Первая `a` вставится успешно,
вторая — нет: `Scope::insert` использует `StringMap::insert`, который не
перезаписывает существующий ключ и возвращает `{iterator, false}`,
поэтому приходит `err_symbold_declared` ("symbol {0} already declared").
Ветка вставки, которая не прошла, параметр в `Params` **не добавляет** —
вызываемые `F(1, 2)` далее видят только первую (валидную) `a`, ошибок
количества параметров при вызове не возникает. Аналогично отбрасывается
повторное объявление локальной переменной и одноимённая переменная поверх
параметра (см. `lab/tests/scope-func-and-local.mod` — тоже
`symbol a already declared`).

---

## 4. Где определены диагностические сообщения?

Сообщения — единый перечень в `include/tinylang/Basic/Diagnostic.def`
(макрос `DIAG(ID, Level, Msg)`): уровень (`Error`/`Warning`/`Note`)
и формат-строка с параметрами в стиле `{0}`, `{1}`. Например:

```
DIAG(err_types_for_operator_not_compatible, Error,
     "types not compatible for operator {0}")
DIAG(err_while_expr_must_be_bool, Error,
     "expression of IF statement must have type BOOLEAN")
```

Инфраструктура:

* `include/tinylang/Basic/Diagnostic.h` — класс `DiagnosticsEngine`
  (обёртка над `SourceMgr`): `report(Loc, DiagID, Args...)` форматирует
  сообщение по ID через `llvm::formatv` и печатает в `errs()` как
  `file:line:col: error: ...`; считает число ошибок (`numErrors()`);
  enum `diag::ID` генерируется разворачиванием `.def` (`#include "Diagnostic.def"`
  в этом же заголовке).
* `lib/Basic/Diagnostic.cpp` — статические таблицы `DiagnosticText[]` и
  `DiagnosticKind[]` (тоже разворачиваются из `.def`), там же
  `getDiagnosticText/getDiagnosticKind`.
* Позиции — `SMLoc`/`SourceMgr` (llvm Support), печать — `SourceMgr::PrintMessage`.

Два известных дефекта текста диагностик (оставлены как есть, т.к. задача
лабораторной — разобраться, где что лежит):

* `err_while_expr_must_be_bool` — текст говорит про IF (см. 1.3);
* `err_symbold_declared` — опечатка в ID (`symbold` вместо `symbol`),
  на сообщение не влияет.

## 5. Поддерживает ли компилятор логические литералы типа BOOLEAN?

**Да**, но не отдельным токеном, а как **предобъявленные константы**:

* В `TokenKinds.def` нет `boolean_literal`; `TRUE`/`FALSE` лексически —
  обычные идентификаторы (`KeywordFilter` не знает таких слов).
* `Sema::initialize()` регистрирует константы `TRUE`/`FALSE`
  (`TrueConst`/`FalseConst`) типа `BOOLEAN` с литералами `BooleanLiteral`
  (AST.h: `EK_Bool`).
* `Sema::actOnVariable` сопоставляет идентификатор `TRUE` с `TrueConst`
  и подставляет `TrueLiteral` вместо `ConstantAccess` — то есть
  литерал в дереве — это `BooleanLiteral`, а не ссылка на константу.
* `AND/OR/NOT` — ключевые слова (`tok::kw_AND/OR/NOT`), их типы проверяются
  в `isOperatorForType` (нужны `BOOLEAN`); константная свёртка
  (`TRUE AND FALSE` → `FALSE`, `NOT TRUE` → `FALSE` и т.п.) выполняется
  прямо в `Sema::actOnTerm` / `actOnSimpleExpression` / `actOnPrefixExpression`.
* В кодогенераторе (lec4) `BooleanLiteral` → `ConstantInt` типа `Int1Ty`
  (`CGProcedure::emitExpr`), т.е. литералы участвуют и в генерации IR.
* Итого: запись `b := TRUE; IF b THEN ...` корректно компилируется
  (см. `boolean-var.mod` в лабораторной 4); при этом отдельного типа/токена
  `BOOLEAN_LITERAL` в языке нет — это согласованное проектное решение.

---

## Приложение: список тестов (lab/tests/)

| Файл | Что проверяет | Ожидание |
|------|----------------|----------|
| `add-number-and-string.mod` | `1 + "2"` | принимается молча (дефект: строки не поддержаны, `parseFactor` не репортит) |
| `add-int-bool.mod` | `1 + TRUE` | `error: types not compatible for operator +` |
| `while-int-condition.mod` | `WHILE x` | `error: ... must have type BOOLEAN` |
| `if-int-condition.mod` | `IF x` | то же для IF |
| `return-10-in-procedure.mod` | `RETURN 10` в PROCEDURE | `error: Procedure does not allow RETURN with value` |
| `return10-type-ok.mod` | `RETURN 10` в FUNCTION | без ошибок |
| `scope-shadow.mod` | одно имя в модуле и процедуре | без ошибок (тень) |
| `duplicate-function-params.mod` | `F(a, a: INTEGER)` | `error: symbol a already declared` + `error: wrong number of parameters` |
| `scope-func-and-local.mod` | параметр + локальная `a` | `error: symbol a already declared` |

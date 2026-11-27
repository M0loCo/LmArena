# Лабораторная работа №1 — сборка clang из исходников; пример 07-calc
# (лекция 1, «The Structure of a Compiler», Nacke2024, глава 2)

Среда: x86-64 GNU/Linux (Debian 12), 2 vCPU, 3 ГБ RAM, Python 3.11.
Сборка выполнена по материалам `00-build-llvm/` (скрипты приведены к рабочему виду).

---

## 1. Сборка из исходников clang для генерации кода на платформе x86-64 GNU/Linux

### 1.1 Что поправлено в скриптах (по сравнению с выложенными материалами)

| Файл | Было | Стало |
|------|------|-------|
| `00-build-llvm/build.sh` | `cmake --build builD` (опечатка) | `cmake --build build` |
| `00-build-llvm/install.sh` | `ninja -S build install` (неверный флаг) | `ninja -C build install` |
| `00-build-llvm/fetch.sh` | `git clone` без указания тега | `--depth 1 --branch llvmorg-17.0.6` |
| `00-build-llvm/config.sh` | `RelWithDebInfo`, `clang;lld;openmp`, без ограничения target | `Release`, `clang;lld`, только `X86`, без openmp, тесты/примеры выключены (иначе >30 ГБ диска и >8 ГБ RAM — не собирается на типовой лабораторной машине) |

Полный текст изменённых скриптов — в каталоге `00-build-llvm/`.

### 1.2 Фактически выполненные шаги

Вместо полного `git clone` (~4 ГБ истории) взят официальный архив тега
`llvmorg-17.0.6` (тот же релиз, на котором написан Nacke2024, Learn LLVM 17):

```bash
curl -sLO https://codeload.github.com/llvm/llvm-project/tar.gz/refs/tags/llvmorg-17.0.6
tar xzf llvm-17.0.6.tar.gz

python3 -m venv tools-venv && tools-venv/bin/pip install cmake ninja   # cmake 4.4.5, ninja 1.13.2

cmake -S llvm-project-llvmorg-17.0.6/llvm -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DLLVM_ENABLE_PROJECTS="clang;lld" \
      -DLLVM_TARGETS_TO_BUILD=X86 \
      -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_EXAMPLES=OFF \
      -DLLVM_ENABLE_ASSERTIONS=OFF \\
      -DLLVM_ENABLE_ZLIB=OFF -DLLVM_ENABLE_TERMINFO=OFF \
      -DLLVM_ENABLE_LIBEDIT=OFF -DLLVM_ENABLE_LIBXML2=OFF \
      -DLLVM_OPTIMIZED_TABLEGEN=ON -DCLANG_INCLUDE_TESTS=OFF \
      -DCMAKE_INSTALL_PREFIX=$HOME/opt/clang

ninja -C build -j2 clang lld lli llc opt llvm-as
ninja -C build install
./clang-env.sh   # PATH=$HOME/opt/clang/bin:...
```

Результат (полный лог — `lab1/llvm-build.log`, если сохранён):

```
$ clang --version
clang version 17.0.6
Target: x86_64-pc-linux-gnu
Thread model: posix
$ ld.lld --version
LLD 17.0.6 (/.../lld)
```

Сборка: `llvmorg-17.0.6`, Release, только X86 target, проекты clang и lld
(openmp из исходного варианта скрипта исключён — для лабораторных не нужен,
требует отдельного runtime и на x86-only сборке ничего не даёт).
Собраны также `lli`, `llc`, `opt`, `llvm-as` — они нужны для лабораторных 3–4.

### 1.3 Замечания по «честной» сборке (что важно на защите)

* `RelWithDebInfo` (вариант из лекции) собирает debug-инфо и раздувает каталог
  сборки до десятков ГБ; `Release` — то же дерево без отладочной информации.
* `LLVM_TARGETS_TO_BUILD=X86` — не собираются AArch64/ARM/RISCV/WebAssembly и
  т.д.; для x86-64 GNU/Linux этого достаточно.
* `LLVM_OPTIMIZED_TABLEGEN=ON` — tablegen в Release-режиме, критично при малой RAM.
* assertions выключены — как в релизных сборках.
* Хост — именно x86-64 GNU/Linux: `llvm-config --host-target` → `X86`.

---

## 2. Пример 07-calc

### 2.1 Сборка

```bash
cd 07-calc
cmake -S . -B build -G Ninja \
      -DLLVM_DIR=$HOME/opt/clang/lib/cmake/llvm -DCMAKE_BUILD_TYPE=Release
ninja -C build
```

### 2.2 Запуск для выражения `with x, y: x + y / 2`

```bash
./build/calc "with x, y: x + y / 2"
```

Вывод (полный — `lab1/calc-output.ll`):

```llvm
; ModuleID = 'calc.expr'
source_filename = "calc.expr"

@x.str = private constant [2 x i8] c"x\00"
@y.str = private constant [2 x i8] c"y\00"

define i32 @main(i32 %0, ptr %1) {
entry:
  %2 = call i32 @calc_read(ptr @x.str)
  %3 = call i32 @calc_read(ptr @y.str)
  %4 = sdiv i32 %3, 2
  %5 = add nsw i32 %2, %4
  call void @calc_write(i32 %5)
  ret i32 0
}

declare i32 @calc_read(ptr)

declare void @calc_write(i32)
```

Обратите внимание на порядок инструкций: `sdiv` (вычисление `y / 2`) идёт до
`add` — ровно как обходится AST постфиксным (обратно польским) способом
(`ToIRVisitor::visit(BinaryOp&)`: сначала левый и правый поддеревья, потом операция).

### 2.3 Семантическая проверка деления на 0 — ДОБАВЛЕНА

Реализация: `src/AST.h` (виртуальный `Expr::constValue(long long &)`
с константной свёрткой в `Factor` и `BinaryOp`), `src/Sema.cpp`
(новый посетитель `DivZeroCheck`, запускается из `Sema::semantic` после
существующего `DeclCheck`).

Поведение:

Фактический вывод (полный — `lab1/calc-divzero.log`; сборка в `/opt/build/calc`):

```
$ calc "with x: x / 0"
Division by zero
Semantic errors occured            # exit=1

$ calc "with x: x / (2 - 2)"        # свёртка констант
Division by zero
Semantic errors occured

$ calc "with x: x / (4 - 1 - 3)"    # то же самое через произвольное подвыражение
Division by zero
Semantic errors occured

$ calc "with x: (x / 0) + 1"        # делитель внутри поддерева
Division by zero
Semantic errors occured

$ calc "with x: x / 2"              # валидный случай
(exit=0, IR сгенерирован)

$ calc "with a, b: 1 + c"           # старая проверка по-прежнему работает
Variable c not declared
Semantic errors occured

$ calc "with a, a: 1"               # повторное объявление — тоже работает
Variable a already declared
Semantic errors occured
```

Границы проверки: статически отвергаются только **константные** делители
(`0`, `00`, `(2-2)`, `(1*3-3)`…). Для неконстантного делителя деление на ноль
выявится только во время выполнения — для этого нужна либо вставка runtime-проверки
(RTL `rtcalc.c` мог бы проверять `b == 0` и печатать диагностику), либо анализ
диапазонов значений (abstract interpretation); обе вещи за рамками задания.

Как устроено: `BinaryOp::constValue` рекурсивно вычисляет поддерево, если все
листья — константные `Factor Number`; `DivZeroCheck::visit(BinaryOp &)` для
`BinaryOp::Div` запрашивает `constValue` правого операнда и при нуле печатает
`Division by zero` и выставляет флаг ошибки, после чего драйвер печатает
`Semantic errors occured` и завершается с `EXIT_FAILURE` (код 1).

### 2.4 AST выражения `with x: 1 - 2 * x`

Типы узлов (из `07-calc/src/AST.h`): `WithDecl` (список имён + выражение),
`BinaryOp` (оператор: `Plus|Minus|Mul|Div`, дети `Expr*`), `Factor`
(`Ident` либо `Number`). Скобки в AST не сохраняются (устраняются парсером).

```
WithDecl  Vars=[x]
└── BinaryOp(Minus)
    ├── Factor(Number 1)
    └── BinaryOp(Mul)
        ├── Factor(Number 2)
        └── Factor(Ident x)
```

Рисунок — `lab1/ast-1-2x.png` (построен по этому дереву, оформление:
WithDecl — синий, BinaryOp — зелёный, Factor — жёлтый).

Соглашения:
* приоритет `*` выше `-` ⇒ вычитание — корень, умножение — правый ребёнок;
* листья — `Factor`, не `Expr`: у `BinaryOp` всегда два ребёнка-`Expr`.

---

## 3. Nacke2024, глава 2 «The Structure of a Compiler» — что из этого есть в примерах

* Три классические фазы: front end (lexing/parsing/sema) → IR → back end
  (инструкции → MC → encoding). Примеры `01-compile`, `02-clang-ir`,
  `03-ir-cfg`, `04-clang-ir-opts`, `05-code-gen` разбирают это на живом `clang`.
* 07-calc — минимальный сквозной пример всех фаз на одном выражении.
* Связь с лабораторной 2: TinyLang — то же самое (lexer → parser → sema),
  только с объявлениями, процедурами и областями видимости; с лабораторной 3–4:
  «front end» достроен генерацией LLVM IR.

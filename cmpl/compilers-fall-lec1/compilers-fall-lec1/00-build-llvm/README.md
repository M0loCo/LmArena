# Сборка clang из исходников (x86-64 GNU/Linux)

Лабораторная использует LLVM 17 (`llvmorg-17.0.6`) — тот же мажор, что в
Nacke2024 «Learn LLVM 17». Скрипты в этой папке починены и приведены к
фактически использованной конфигурации.

## Что было исправлено в скриптах

* `build.sh` — `cmake --build builD` → `cmake --build build` (опечатка).
* `install.sh` — `ninja -S build install` → `ninja -C build install`.
* `fetch.sh` — `git clone --depth 1 --branch llvmorg-17.0.6` (shallow,
  фиксированный тег; полный клон — >4 ГБ).
* `config.sh` — `Release` вместо `RelWithDebInfo`, только `X86` вместо всех
  целей, `clang;lld`, без `openmp`, отключены тесты/примеры/бенчмарки,
  `LLVM_OPTIMIZED_TABLEGEN=ON` (важно при малой RAM).

## Фактическая сборка (как сделано)

Исходники взяты официальным архивом тега с GitHub (codeload), что быстрее
и дешевле по диску, чем `git clone` (равнозначно по содержимому):

```bash
curl -sLO https://codeload.github.com/llvm/llvm-project/tar.gz/refs/tags/llvmorg-17.0.6
tar xzf llvm-17.0.6.tar.gz
python3 -m venv /opt/tools-venv && /opt/tools-venv/bin/pip install cmake ninja

cmake -S llvm-project-llvmorg-17.0.6/llvm -B build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DLLVM_ENABLE_PROJECTS="clang;lld" \
      -DLLVM_TARGETS_TO_BUILD=X86 \
      -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_EXAMPLES=OFF \
      -DLLVM_INCLUDE_BENCHMARKS=OFF -DLLVM_ENABLE_ASSERTIONS=OFF \
      -DLLVM_ENABLE_ZLIB=OFF -DLLVM_ENABLE_TERMINFO=OFF \
      -DLLVM_ENABLE_LIBEDIT=OFF -DLLVM_ENABLE_LIBXML2=OFF \
      -DLLVM_OPTIMIZED_TABLEGEN=ON -DCLANG_INCLUDE_TESTS=OFF \
      -DCMAKE_INSTALL_PREFIX=$HOME/opt/clang

ninja -C build -j2 clang lld lli llc opt llvm-as   # -j2: 2 vCPU / 3 ГБ RAM
ninja -C build install
```

Ключевые свойства сборки:

* платформа генерации кода: **x86-64 GNU/Linux** (`LLVM_TARGETS_TO_BUILD=X86`,
  `target triple x86_64-pc-linux-gnu`);
* проекты: `clang` (драйвер, clang++, clang-install), `lld` (ld.lld), плюс
  утилиты LLVM, нужные лабораторным 3–4 (`lli`, `llc`, `opt`, `llvm-as`);
* без тестов/примеров/бенчмарков — только компилятор и библиотеки;
* `ninja clang lld ...` вместо `ninja all` — не собираются лишние clang-tools
  (экономит ~1300 из 3775 целей).

## Проверка

```bash
. ./clang-env.sh
clang --version    # clang version 17.0.6
ld.lld --version   # LLD 17.0.6
llc --version      # LLVM (http://llvm.org/): LLVM version 17.0.6
opt --version
```

Итоговые бинарники: `$HOME/opt/clang/bin/{clang,clang++,ld.lld,lli,llc,opt,llvm-as}`,
библиотеки и CMake-пакет: `$HOME/opt/clang/lib`, в т.ч.
`$HOME/opt/clang/lib/cmake/llvm/LLVMConfig.cmake` для `find_package(LLVM)`.

# Лабораторная работа №3 — LLVM IR: реализация GCD
# (лекция 3, «LLVM IR»)

Задание: **реализовать на LLVM IR функцию вычисления GCD, переписать gcd.c
на LLVM IR; объяснить трансляцию аргументов функции и цикла.**

Файлы: исходный `../gcd.c` (из материалов лекции) и `../gcd.ll`
(ручной SSA-вариант) — лежат рядом, одной папке.

## 1. Исходный gcd.c (лекция 3)

```c
#include <stdio.h>

int gcd(int a, int b)
{
    while (b != 0) {
        int t = a % b;
        a = b;
        b = t;
    }
    return a;
}

int main()
{
    printf("gcd(12, 15) = %d\n", gcd(12, 15));
    return 0;
}
```

## 2. Переписано на LLVM IR (`gcd.ll` рядом с `gcd.c`)

```llvm
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

(полный файл с `main`, печатающим `gcd(12, 15) = 3`, — в `gcd.ll`).

## 3. Трансляция аргументов функции

* Типы C ↔ IR (строго типизировано): `int` → `i32`, `long long` → `i64`,
  `char` → `i8`, `bool` → `i1`. `srem` принимает только целые одинаковой
  разрядности; «случайно» сложить i32 и i64 нельзя.
* Сигнатура: `gcd(int, int)` → `i32 (i32, i32)` — функция, первый класс
  значений; `call i32 @gcd(i32 12, i32 15)` передаёт параметры по значению.
* По соглашению о вызовах x86-64 System V AMD64 первые целочисленные
  аргументы идут в регистрах `%rdi` и `%rsi`; остальное (кому сохраняются,
  выравнивание стека и т.п.) зафиксировано `target triple =
  "x86_64-unknown-linux-gnu"` и datalayout в модуле.
* Имена `%a`, `%b` — только для читаемости; машинный код их не видит.
* `entry`/`cond`/`body`/`exit` — базовые блоки (терминированы `br`/`ret`).
* Чистая SSA-форма: значения нельзя "присвоить"; перенос `a:=b; b:=t`
  выражен phi-функциями. В `-O0`-выводе clang вместо этого `alloca` +
  `load`/`store`, которые `mem2reg` убирает, превращая в те же phi.

## 4. Трансляция цикла `while`

`while (b != 0) { int t = a % b; a = b; b = t; }` порождает 4 блока
(3 новых + предшествующий):

| Блок | Роль | Предшественники |
|------|------|------------------|
| `entry` | пролог; безусловный переход в заголовок | — |
| `cond`  | заголовок: phi сливают значения из entry и body; `icmp eq` + `br i1` | entry, body |
| `body`  | тело: `t = srem a, b`; переход в заголовок | cond |
| `exit`  | выход из цикла, `ret i32` | cond |

Phi-функции в заголовке:

```
%a.phi = phi i32 [ %a, %entry ], [ %b.phi, %body ]
%b.phi = phi i32 [ %b, %entry ], [ %t, %body ]
```

* Один вход на каждого предшественника блока (`cond` имеет двух: `entry`
  и `body`) — иначе верификатор LLVM выдаст ошибку `PHINode should have one entry for each predecessor`.
* На первой итерации значения берутся из `entry` (исходные аргументы),
  на последующих — из `body` (перенесённые).
* `icmp eq i32 %b.phi, 0` даёт `i1` — условие для `br i1`.
* `srem` — остаток со знаком, что соответствует `%` в C для `int`.

## 5. Сравнение с IR, сгенерированным clang'ом

```bash
cd ~/cmpl/lab3
clang -O0 -S -emit-llvm gcd.c -o gcd-clang-O0.ll
clang -O1 -S -emit-llvm gcd.c -o gcd-clang-O1.ll
```

* `gcd-clang-O0.ll` (неоптимизированный): `alloca` под `a`, `b`, `t`,
  `store` аргументов, `load` перед каждым использованием, цикл через
  блоки вида `while.cond`/`while.body` с `br`. Имя C-функции в IR — `@gcd`
  (манглирование есть только у C++; C++-версия была бы `_Z3gcdii`).
  Нумерованные виртуальные регистры (`%3`, `%4`…) вместо имён.
* `gcd-clang-O1.ll` (оптимизированный): `alloca` отсутствуют (mem2reg),
  остались phi в заголовке — т.е. ручной `gcd.ll` структурно совпадает
  с выводом clang -O1 (с точностью до имён и атрибутов функций).

## 6. Запуск и проверка — ВЫПОЛНЕНО на машине пользователя

(Ubuntu, LLVM/clang 24.0.0git из лабы 1, `~/opt/clang`, каталог `~/cmpl/lab3`).

```bash
cd ~/cmpl/lab3
export PATH=$HOME/opt/clang/bin:$PATH
which clang lli
lli gcd.ll
clang gcd.ll -o gcd && ./gcd
clang gcd.c -o gcd_c && ./gcd_c
clang -O0 -S -emit-llvm gcd.c -o gcd-clang-O0.ll
clang -O1 -S -emit-llvm gcd.c -o gcd-clang-O1.ll
grep -nE 'alloca|phi' gcd-clang-O1.ll
```

Реальный вывод (`lli`):

```
gcd(12, 15) = 3
```

То же самое из собранного ELF (`./gcd`, `./gcd_c`) — тоже `gcd(12, 15) = 3`.

Реальный `grep -nE 'alloca|phi' gcd-clang-O1.ll` (alloca отсутствуют — SSA
после `mem2reg`; вместо имён — пронумерованные регистры):

```
14:  %5 = phi i32 [ %6, %4 ], [ %0, %2 ]
15:  %6 = phi i32 [ %7, %4 ], [ %1, %2 ]
21:  %10 = phi i32 [ %0, %2 ], [ %6, %4 ]
30:  %2 = phi i32 [ %3, %1 ], [ 12, %0 ]
31:  %3 = phi i32 [ %4, %1 ], [ 15, %0 ]
```

Структура `gcd-clang-O1.ll` совпадает с ручным `gcd.ll`: phi в заголовке
цикла, `icmp eq i32 …, 0`, `srem i32`, `br i1`, три базовых блока цикла.
Отличия только в именовании (`%0`, `%5`… вместо `%a.phi`/`%b.phi`) и в том,
что clang склеил `main` и вызывает тот же код.

## 7. Итог и связь с остальными лабами

* Типы строго типизированы: `i32` аргументы, `i1` условия, `srem i32`.
* Цикл = базовые блоки + phi; присваивания в IR нет (SSA).
* Именно такую схему (`entry` → `while.cond` → `while.body` → `after.while`,
  phi в заголовке) реализует кодогенератор TinyLang — см. лабораторную 4.

Проверено на машине пользователя: `lli gcd.ll`, `clang gcd.ll -o gcd`,
`clang gcd.c -o gcd_c` — во всех случаях печатается `gcd(12, 15) = 3`;
сравнение с IR от `clang -O0/-O1` — в §5–§6 выше.

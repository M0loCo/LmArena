MODULE ScopeFuncAndLocal;
PROCEDURE G(a: INTEGER) : INTEGER;
VAR a: INTEGER;
BEGIN
  a := a + 1;
  RETURN a;
END G;
VAR y: INTEGER;
BEGIN
  y := G(10);
END ScopeFuncAndLocal.

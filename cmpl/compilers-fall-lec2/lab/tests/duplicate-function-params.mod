MODULE DuplicateFunctionParams;
PROCEDURE F(a, a: INTEGER) : INTEGER;
BEGIN
  RETURN a;
END F;
VAR y: INTEGER;
BEGIN
  y := F(1, 2);
END DuplicateFunctionParams.

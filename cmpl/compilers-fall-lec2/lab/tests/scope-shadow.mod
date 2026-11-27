MODULE ScopeShadow;
VAR x: INTEGER;
PROCEDURE Shadow();
VAR x: INTEGER;
BEGIN
  x := 1;
END Shadow;
BEGIN
  x := 42;
  Shadow();
END ScopeShadow.

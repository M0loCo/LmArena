MODULE BoolPhi;
PROCEDURE Toggle(n: INTEGER) : BOOLEAN;
VAR b: BOOLEAN;
BEGIN
  b := FALSE;
  WHILE n > 0 DO
    b := NOT b;
    n := n - 1;
  END;
  RETURN b;
END Toggle.
END BoolPhi.

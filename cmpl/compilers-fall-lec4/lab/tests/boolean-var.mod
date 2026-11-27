MODULE BoolVar;
VAR b: BOOLEAN;
BEGIN
  b := TRUE;
  IF b THEN
    b := FALSE;
  END;
  WHILE b DO
    b := FALSE;
  END;
END BoolVar.

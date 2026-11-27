MODULE BoolVar;
VAR b: BOOLEAN;
PROCEDURE Main();
BEGIN
  b := TRUE;
  IF b THEN
    b := FALSE;
  END;
  WHILE b DO
    b := FALSE;
  END;
END Main;
END BoolVar.

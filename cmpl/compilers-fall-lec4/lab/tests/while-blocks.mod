MODULE WhileBlocks;
PROCEDURE Sum(n: INTEGER) : INTEGER;
VAR s: INTEGER;
BEGIN
  s := 0;
  WHILE n > 0 DO
    s := s + n;
    n := n - 1;
  END;
  RETURN s;
END Sum;
END WhileBlocks.

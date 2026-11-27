MODULE BoolExpr;
PROCEDURE Between(x: INTEGER) : BOOLEAN;
BEGIN
  RETURN (x > 0) AND (x < 100);
END Between;
PROCEDURE Either(a, b: BOOLEAN) : BOOLEAN;
BEGIN
  RETURN a OR b;
END Either;
END BoolExpr.

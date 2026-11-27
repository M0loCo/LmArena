#ifndef AST_H
#define AST_H

#include <iostream>

#include "llvm/ADT/SmallVector.h"
#include "llvm/ADT/StringRef.h"

//#define PARSER_VERBOSE

class AST;
class Expr;
class Factor;
class BinaryOp;
class WithDecl;

class ASTVisitor {
public:
  virtual void visit(AST &) {};
  virtual void visit(Expr &) {};
  virtual void visit(Factor &) = 0;
  virtual void visit(BinaryOp &) = 0;
  virtual void visit(WithDecl &) = 0;
};

class AST {
public:
  virtual ~AST() {}
  virtual void accept(ASTVisitor &V) = 0;
};

class Expr : public AST {
public:
  Expr() {}
  virtual bool constValue(long long &V) const {
    (void)V;
    return false;
  }
};

class Factor : public Expr {
public:
  enum ValueKind { Ident, Number };

private:
  ValueKind Kind;
  llvm::StringRef Val;

public:
  Factor(ValueKind Kind, llvm::StringRef Val)
      : Kind(Kind), Val(Val)
  {
    #ifdef PARSER_VERBOSE
    std::cout << "Factor: " << Kind << " Val = " << Val.str() << "\n";
    #endif
  }
  ValueKind getKind() { return Kind; }
  llvm::StringRef getVal() { return Val; }
  bool constValue(long long &V) const override {
    if (Kind != Number)
      return false;
    unsigned long long U = 0;
    if (Val.getAsInteger(10, U))
      return false;
    V = static_cast<long long>(U);
    return true;
  }
  virtual void accept(ASTVisitor &V) override {
    V.visit(*this);
  }
};

class BinaryOp : public Expr {
public:
  enum Operator { Plus, Minus, Mul, Div };

private:
  Expr *Left;
  Expr *Right;
  Operator Op;

public:
  BinaryOp(Operator Op, Expr *L, Expr *R)
      : Op(Op), Left(L), Right(R)
  {
    #ifdef PARSER_VERBOSE
    std::cout << "BinaryOp: " << Op << "\n";
    #endif
  }
  Expr *getLeft() { return Left; }
  Expr *getRight() { return Right; }
  Operator getOperator() { return Op; }
  bool constValue(long long &V) const override {
    if (!Left || !Right)
      return false;
    long long L = 0, R = 0;
    if (!Left->constValue(L) || !Right->constValue(R))
      return false;
    switch (Op) {
    case Plus:  V = L + R; return true;
    case Minus: V = L - R; return true;
    case Mul:   V = L * R; return true;
    case Div:
      if (R == 0)
        return false;
      V = L / R;
      return true;
    }
    return false;
  }
  virtual void accept(ASTVisitor &V) override {
    V.visit(*this);
  }
};

class WithDecl : public AST {
  using VarVector = llvm::SmallVector<llvm::StringRef, 8>;
  VarVector Vars;
  Expr *E;

public:
  WithDecl(llvm::SmallVector<llvm::StringRef, 8> Vars,
           Expr *E)
      : Vars(Vars), E(E)
  {
    #ifdef PARSER_VERBOSE
    std::cout << "WithDecl: ";
    for (auto it = Vars.begin(); it != Vars.end(); it++) {
      std::cout << it->str() << " ";
    }
    std::cout << "\n";
    #endif
  }
  VarVector::const_iterator begin() { return Vars.begin(); }
  VarVector::const_iterator end() { return Vars.end(); }
  Expr *getExpr() { return E; }
  virtual void accept(ASTVisitor &V) override {
    V.visit(*this);
  }
};
#endif

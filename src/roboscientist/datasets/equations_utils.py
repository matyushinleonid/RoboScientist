import sympy as snp
import networkx as nx
import numpy as np
import re
from . import equations_settings


def construct_symbol(name):
    return "Symbol('{}')".format(name)


def generate_random_tree_with_prior_on_arity(n=10, max_degree=3, degreeness=1):
    """
    Generate random tree with degree no more than max_degree and n + 2 nodes
    """
    nums = np.arange(1, n + 1)
    prufer_sequence = [0]
    while len(prufer_sequence) < n:
        # delete num with degree >= max_degree
        for val, count in zip(*np.unique(prufer_sequence, return_counts=True)):
            if count >= max_degree:
                nums = np.delete(nums, np.argwhere(nums == val))

        proba = np.ones_like(nums)
        for val, count in zip(*np.unique(prufer_sequence, return_counts=True)):
            proba[np.argwhere(nums == val)] += count

        proba = proba ** degreeness
        proba = proba / proba.sum()
        num = np.random.choice(nums, p=proba)
        prufer_sequence.append(num)

    np.random.shuffle(prufer_sequence)
    prufer_sequence = prufer_sequence[:n]
    return nx.bfs_tree(nx.algorithms.tree.coding.from_prufer_sequence(prufer_sequence), 0)


def generate_random_formula_on_graph(D, n_symbols, setup=equations_settings.setup_general):
    setup()

    symbols = [construct_symbol("x{}".format(i)) for i in range(n_symbols)]
    for node in D.nodes():
        # leaf -> either constant or symbol
        if D.out_degree(node) == 0:
            if np.random.choice([0, 1]):
                D.nodes[node]["expr"] = np.random.choice(symbols)
            else:
                D.nodes[node]["expr"] = str(np.random.choice(equations_settings.constants))
        # functions of arity one
        elif D.out_degree(node) == 1:
            f = np.random.choice(equations_settings.functions_with_arity[1])
            D.nodes[node]["expr"] = f
        # functions with arity D.out_degree(node) + any arity
        else:
            D.nodes[node]["expr"] = np.random.choice(
                equations_settings.functions_with_arity[0] + equations_settings.functions_with_arity.get(D.out_degree(node), [""])
            )

    return D


class _EnumerateConstant:
    def __init__(self):
        self.const_counter = 0

    def __call__(self, match):
        const = construct_symbol(equations_settings.CONST_BASE_NAME + str(self.const_counter))
        self.const_counter += 1
        return const


def enumerate_constants_in_expression(expr: str):
    """
    const + x0**const -> const_1 + x0**const_2
    :param expr: str
    :return:
    """
    enumerate_constants = _EnumerateConstant()
    return re.sub(r"Symbol\('{}'\)".format(equations_settings.CONST_BASE_NAME), enumerate_constants, expr)


def graph_to_expression(D, node=0):
    """
    Converts graph to expression
    :param D: nx.DiGraph, tree where each node has attribute `expr`
    :param node: int, root of tree (or subtree)
    :return:
    """
    if D.out_degree(node) == 0:
        expr = D.nodes[node]['expr']
    else:
        if D.nodes[node]['expr']:
            expr = [
                D.nodes[node]['expr'],
                "(",
                ",".join([graph_to_expression(D, node=child) for child in D[node]]),
                ")"
            ]
            expr = "".join(expr)
            # checking if expr contains constants only as symbols
            # if so => rename it as one constant
            # i.e. sin(const) -> const, e^{const + 5} -> const, etc.
            symbols = re.findall(r'Symbol\((.*?)\)', expr)
            if len(symbols) and all([equations_settings.CONST_BASE_NAME in symbol for symbol in symbols]):
                expr = construct_symbol(equations_settings.CONST_BASE_NAME)
        else:
            # None => assuming that arity == 1
            # and thus we do not nest it
            expr = graph_to_expression(D, node=list(D[node].keys())[0])

    if node == 0:
        # post-factum enumeration of consts
        # firstly we use sympy to simplify expression
        expr = snp.simplify(snp.sympify(expr))  # eval
        # secondly we numerate constants if any
        expr = enumerate_constants_in_expression(snp.srepr(expr))
        return snp.simplify(snp.sympify(expr))  # eval
    else:
        return expr


def expr_to_tree(expr, D=None, node=None):
    if D is None:
        D = nx.DiGraph()
        node = 0

    if expr.func.is_symbol:
        D.add_node(node, expr="Symbol('{}')".format(expr.name))
    elif expr.is_Function or expr.is_Add or expr.is_Mul or expr.is_Pow:
        D.add_node(node, expr=type(expr).__name__)
    elif expr.is_constant():
        D.add_node(node, expr=str(expr))

    parent_node = node
    for i, child in enumerate(expr.args):
        D.add_edge(parent_node, node + 1)
        D, node = expr_to_tree(child, D=D, node=node + 1)

    return D, node


def expr_to_postfix(expr):
    """
    Returns postorder traversal (i.e. in polish notation) of the symbolic expression
    """

    post = []
    post_arity = []
    for expr_node in snp.postorder_traversal(expr):
        post_arity.append(len(expr_node.args))
        if expr_node.func.is_symbol:
            post.append(expr_node.name)
        elif expr_node.is_Function or expr_node.is_Add or expr_node.is_Mul or expr_node.is_Pow:
            post.append(type(expr_node).__name__)
        elif expr_node.is_constant():
            post.append(float(expr_node))

    return post, post_arity


def postfix_to_expr(post, post_arity):
    """
    Returns expression from polish notation
    https://en.wikipedia.org/wiki/Shunting-yard_algorithm
    """
    stack = []

    def symbol_or_constant(x):
        if isinstance(x, str):
            return "Symbol('{}')".format(x)
        else:
            return str(x)

    for arg, arg_arity in zip(post, post_arity):
        if arg_arity == 0:
            stack.append(symbol_or_constant(arg))
        else:
            stack_temporary = []
            for _ in range(arg_arity):
                stack_temporary.append(stack.pop())
            expr = [
                arg,
                "(",
                ",".join([_arg for _arg in stack_temporary[::-1]]),
                ")"
            ]
            expr = "".join(expr)
            stack.append(expr)

    return snp.sympify(stack[0])  # eval


def expr_to_infix(expr):
    """
    Returns preorder traversal of the symbolic expression
    """

    pre = []
    pre_arity = []
    for expr_node in snp.preorder_traversal(expr):
        pre_arity.append(len(expr_node.args))
        if expr_node.func.is_symbol:
            pre.append(expr_node.name)
        elif expr_node.is_Function or expr_node.is_Add or expr_node.is_Mul or expr_node.is_Pow:
            pre.append(type(expr_node).__name__)
        elif expr_node.is_constant():
            pre.append(float(expr_node))
    return pre, pre_arity
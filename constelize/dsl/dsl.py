from .arc_types import *
import json


def identity(
    x: Any
) -> Any:
    """ identity function """
    return x


def add(
    a: Numerical,
    b: Numerical
) -> Numerical:
    """ addition """
    if isinstance(a, int) and isinstance(b, int):
        return a + b
    elif isinstance(a, tuple) and isinstance(b, tuple):
        return (a[0] + b[0], a[1] + b[1])
    elif isinstance(a, int) and isinstance(b, tuple):
        return (a + b[0], a + b[1])
    return (a[0] + b, a[1] + b)


def subtract(
    a: Numerical,
    b: Numerical
) -> Numerical:
    """ subtraction """
    if isinstance(a, int) and isinstance(b, int):
        return a - b
    elif isinstance(a, tuple) and isinstance(b, tuple):
        return (a[0] - b[0], a[1] - b[1])
    elif isinstance(a, int) and isinstance(b, tuple):
        return (a - b[0], a - b[1])
    return (a[0] - b, a[1] - b)


def multiply(
    a: Numerical,
    b: Numerical
) -> Numerical:
    """ multiplication """
    if isinstance(a, int) and isinstance(b, int):
        return a * b
    elif isinstance(a, tuple) and isinstance(b, tuple):
        return (a[0] * b[0], a[1] * b[1])
    elif isinstance(a, int) and isinstance(b, tuple):
        return (a * b[0], a * b[1])
    return (a[0] * b, a[1] * b)


def divide(
    a: Numerical,
    b: Numerical
) -> Numerical:
    """ floor division """
    if isinstance(a, int) and isinstance(b, int):
        return a // b
    elif isinstance(a, tuple) and isinstance(b, tuple):
        return (a[0] // b[0], a[1] // b[1])
    elif isinstance(a, int) and isinstance(b, tuple):
        return (a // b[0], a // b[1])
    return (a[0] // b, a[1] // b)


def invert(
    n: Numerical
) -> Numerical:
    """ inversion with respect to addition """
    return -n if isinstance(n, int) else (-n[0], -n[1])


def even(
    n: Integer
) -> Boolean:
    """ evenness """
    return n % 2 == 0


def double(
    n: Numerical
) -> Numerical:
    """ scaling by two """
    return n * 2 if isinstance(n, int) else (n[0] * 2, n[1] * 2)


def halve(
    n: Numerical
) -> Numerical:
    """ scaling by one half """
    return n // 2 if isinstance(n, int) else (n[0] // 2, n[1] // 2)


def flip(
    b: Boolean
) -> Boolean:
    """ logical not """
    return not b


def equality(
    a: Any,
    b: Any
) -> Boolean:
    """ equality """
    return a == b


def contained(
    value: Any,
    container: Container
) -> Boolean:
    """ element of """
    return value in container


def combine(
    a: Container,
    b: Container
) -> Container:
    """ union """
    return type(a)((*a, *b))


def intersection(
    a: FrozenSet,
    b: FrozenSet
) -> FrozenSet:
    """ returns the intersection of two containers """
    return a & b


def difference(
    a: FrozenSet,
    b: FrozenSet
) -> FrozenSet:
    """ set difference """
    return type(a)(e for e in a if e not in b)


def dedupe(
    tup: Tuple
) -> Tuple:
    """ remove duplicates """
    return tuple(e for i, e in enumerate(tup) if tup.index(e) == i)


def order(
    container: Container,
    compfunc: Callable
) -> Tuple:
    """ order container by custom key """
    return tuple(sorted(container, key=compfunc))


def repeat(
    item: Any,
    num: Integer
) -> Tuple:
    """ repetition of item within vector """
    return tuple(item for i in range(num))


def greater(
    a: Integer,
    b: Integer
) -> Boolean:
    """ greater """
    return a > b


def size(
    container: Container
) -> Integer:
    """ cardinality """
    return len(container)


def merge(
    containers: ContainerContainer
) -> Container:
    """ merging """
    return type(containers)(e for c in containers for e in c)


def maximum(
    container: IntegerSet
) -> Integer:
    """ maximum """
    return max(container, default=0)


def minimum(
    container: IntegerSet
) -> Integer:
    """ minimum """
    return min(container, default=0)


def valmax(
    container: Container,
    compfunc: Callable
) -> Integer:
    """ maximum by custom function """
    return compfunc(max(container, key=compfunc, default=0))


def valmin(
    container: Container,
    compfunc: Callable
) -> Integer:
    """ minimum by custom function """
    return compfunc(min(container, key=compfunc, default=0))


def argmax(
    container: Container,
    compfunc: Callable
) -> Any:
    """ largest item by custom order """
    return max(container, key=compfunc)


def argmin(
    container: Container,
    compfunc: Callable
) -> Any:
    """ smallest item by custom order """
    return min(container, key=compfunc)


def mostcommon(
    container: Container
) -> Any:
    """ most common item """
    return max(set(container), key=container.count)


def leastcommon(
    container: Container
) -> Any:
    """ least common item """
    return min(set(container), key=container.count)


def initset(
    value: Any
) -> FrozenSet:
    """ initialize container """
    return frozenset({value})


def both(
    a: Boolean,
    b: Boolean
) -> Boolean:
    """ logical and """
    return a and b


def either(
    a: Boolean,
    b: Boolean
) -> Boolean:
    """ logical or """
    return a or b


def increment(
    x: Numerical
) -> Numerical:
    """ incrementing """
    return x + 1 if isinstance(x, int) else (x[0] + 1, x[1] + 1)


def decrement(
    x: Numerical
) -> Numerical:
    """ decrementing """
    return x - 1 if isinstance(x, int) else (x[0] - 1, x[1] - 1)


def crement(
    x: Numerical
) -> Numerical:
    """ incrementing positive and decrementing negative """
    if isinstance(x, int):
        return 0 if x == 0 else (x + 1 if x > 0 else x - 1)
    return (
        0 if x[0] == 0 else (x[0] + 1 if x[0] > 0 else x[0] - 1),
        0 if x[1] == 0 else (x[1] + 1 if x[1] > 0 else x[1] - 1)
    )


def sign(
    x: Numerical
) -> Numerical:
    """ sign """
    if isinstance(x, int):
        return 0 if x == 0 else (1 if x > 0 else -1)
    return (
        0 if x[0] == 0 else (1 if x[0] > 0 else -1),
        0 if x[1] == 0 else (1 if x[1] > 0 else -1)
    )


def positive(
    x: Integer
) -> Boolean:
    """ positive """
    return x > 0


def toivec(
    i: Integer
) -> IntegerTuple:
    """ vector pointing vertically """
    return (i, 0)


def tojvec(
    j: Integer
) -> IntegerTuple:
    """ vector pointing horizontally """
    return (0, j)


def sfilter(
    container: Container,
    condition: Callable
) -> Container:
    """ keep elements in container that satisfy condition """
    return type(container)(e for e in container if condition(e))


def mfilter(
    container: Container,
    function: Callable
) -> FrozenSet:
    """ filter and merge """
    return merge(sfilter(container, function))


def extract(
    container: Container,
    condition: Callable
) -> Any:
    """ first element of container that satisfies condition """
    return next(e for e in container if condition(e))


def totuple(
    container: FrozenSet
) -> Tuple:
    """ conversion to tuple """
    return tuple(container)


def first(
    container: Container
) -> Any:
    """ first item of container """
    return next(iter(container))


def last(
    container: Container
) -> Any:
    """ last item of container """
    return max(enumerate(container))[1]


def insert(
    value: Any,
    container: FrozenSet
) -> FrozenSet:
    """ insert item into container """
    return container.union(frozenset({value}))


def remove(
    value: Any,
    container: Container
) -> Container:
    """ remove item from container """
    return type(container)(e for e in container if e != value)


def other(
    container: Container,
    value: Any
) -> Any:
    """ other value in the container """
    return first(remove(value, container))


def interval(
    start: Integer,
    stop: Integer,
    step: Integer
) -> Tuple:
    """ range """
    return tuple(range(start, stop, step))


def astuple(
    a: Integer,
    b: Integer
) -> IntegerTuple:
    """ constructs a tuple """
    return (a, b)


def product(
    a: Container,
    b: Container
) -> FrozenSet:
    """ cartesian product """
    return frozenset((i, j) for j in b for i in a)


def pair(
    a: Tuple,
    b: Tuple
) -> TupleTuple:
    """ zipping of two tuples """
    return tuple(zip(a, b))


def branch(
    condition: Boolean,
    a: Any,
    b: Any
) -> Any:
    """ if else branching """
    return a if condition else b


def compose(
    outer: Callable,
    inner: Callable
) -> Callable:
    """ function composition """
    return lambda x: outer(inner(x))


def chain(
    h: Callable,
    g: Callable,
    f: Callable,
) -> Callable:
    """ function composition with three functions """
    return lambda x: h(g(f(x)))


def matcher(
    function: Callable,
    target: Any
) -> Callable:
    """ construction of equality function """
    return lambda x: function(x) == target


def rbind(
    function: Callable,
    fixed: Any
) -> Callable:
    """ fix the rightmost argument """
    n = function.__code__.co_argcount
    if n == 2:
        return lambda x: function(x, fixed)
    elif n == 3:
        return lambda x, y: function(x, y, fixed)
    else:
        return lambda x, y, z: function(x, y, z, fixed)


def lbind(
    function: Callable,
    fixed: Any
) -> Callable:
    """ fix the leftmost argument """
    n = function.__code__.co_argcount
    if n == 2:
        return lambda y: function(fixed, y)
    elif n == 3:
        return lambda y, z: function(fixed, y, z)
    else:
        return lambda y, z, a: function(fixed, y, z, a)


def power(
    function: Callable,
    n: Integer
) -> Callable:
    """ power of function """
    if n == 1:
        return function
    return compose(function, power(function, n - 1))


def fork(
    outer: Callable,
    a: Callable,
    b: Callable
) -> Callable:
    """ creates a wrapper function """
    return lambda x: outer(a(x), b(x))


def apply(
    function: Callable,
    container: Container
) -> Container:
    """ apply function to each item in container """
    return type(container)(function(e) for e in container)


def rapply(
    functions: Container,
    value: Any
) -> Container:
    """ apply each function in container to value """
    return type(functions)(function(value) for function in functions)


def mapply(
    function: Callable,
    container: ContainerContainer
) -> FrozenSet:
    """ apply and merge """
    return merge(apply(function, container))


def papply(
    function: Callable,
    a: Tuple,
    b: Tuple
) -> Tuple:
    """ apply function on two vectors """
    return tuple(function(i, j) for i, j in zip(a, b))


def mpapply(
    function: Callable,
    a: Tuple,
    b: Tuple
) -> Tuple:
    """ apply function on two vectors and merge """
    return merge(papply(function, a, b))


def prapply(
    function,
    a: Container,
    b: Container
) -> FrozenSet:
    """ apply function on cartesian product """
    return frozenset(function(i, j) for j in b for i in a)


def mostcolor(
    element: Element
) -> Integer:
    """ most common color """
    values = [v for r in element for v in r] if isinstance(element, tuple) else [v for v, _ in element]
    return max(set(values), key=values.count)


def leastcolor(
    element: Element
) -> Integer:
    """ least common color """
    values = [v for r in element for v in r] if isinstance(element, tuple) else [v for v, _ in element]
    return min(set(values), key=values.count)


def height(
    piece: Piece
) -> Integer:
    """ height of grid or patch """
    if len(piece) == 0:
        return 0
    if isinstance(piece, tuple):
        return len(piece)
    return lowermost(piece) - uppermost(piece) + 1


def width(
    piece: Piece
) -> Integer:
    """ width of grid or patch """
    if len(piece) == 0:
        return 0
    if isinstance(piece, tuple):
        return len(piece[0])
    return rightmost(piece) - leftmost(piece) + 1


def shape(
    piece: Piece
) -> IntegerTuple:
    """ height and width of grid or patch """
    return (height(piece), width(piece))


def portrait(
    piece: Piece
) -> Boolean:
    """ whether height is greater than width """
    return height(piece) > width(piece)


def colorcount(
    element: Element,
    value: Integer
) -> Integer:
    """ number of cells with color """
    if isinstance(element, tuple):
        return sum(row.count(value) for row in element)
    return sum(v == value for v, _ in element)


def colorfilter(
    objs: Objects,
    value: Integer
) -> Objects:
    """ filter objects by color """
    return frozenset(obj for obj in objs if next(iter(obj))[0] == value)


def sizefilter(
    container: Container,
    n: Integer
) -> FrozenSet:
    """ filter items by size """
    return frozenset(item for item in container if len(item) == n)


def asindices(
    grid: Grid
) -> Indices:
    """ indices of all grid cells """
    return frozenset((i, j) for i in range(len(grid)) for j in range(len(grid[0])))


def ofcolor(
    grid: Grid,
    value: Integer
) -> Indices:
    """ indices of all grid cells with value """
    return frozenset((i, j) for i, r in enumerate(grid) for j, v in enumerate(r) if v == value)


def ulcorner(
    patch: Patch
) -> IntegerTuple:
    """ index of upper left corner """
    return tuple(map(min, zip(*toindices(patch))))


def urcorner(
    patch: Patch
) -> IntegerTuple:
    """ index of upper right corner """
    return tuple(map(lambda ix: {0: min, 1: max}[ix[0]](ix[1]), enumerate(zip(*toindices(patch)))))


def llcorner(
    patch: Patch
) -> IntegerTuple:
    """ index of lower left corner """
    return tuple(map(lambda ix: {0: max, 1: min}[ix[0]](ix[1]), enumerate(zip(*toindices(patch)))))


def lrcorner(
    patch: Patch
) -> IntegerTuple:
    """ index of lower right corner """
    return tuple(map(max, zip(*toindices(patch))))


def crop(
    grid: Grid,
    start: IntegerTuple,
    dims: IntegerTuple
) -> Grid:
    """ subgrid specified by start and dimension """
    return tuple(r[start[1]:start[1]+dims[1]] for r in grid[start[0]:start[0]+dims[0]])


def toindices(
    patch: Patch
) -> Indices:
    """ indices of object cells """
    if len(patch) == 0:
        return frozenset()
    if isinstance(next(iter(patch))[1], tuple):
        return frozenset(index for value, index in patch)
    return patch


def recolor(
    value: Integer,
    patch: Patch
) -> Object:
    """ recolor patch """
    return frozenset((value, index) for index in toindices(patch))


def shift(
    patch: Patch,
    directions: IntegerTuple
) -> Patch:
    """ shift patch """
    if len(patch) == 0:
        return patch
    di, dj = directions
    if isinstance(next(iter(patch))[1], tuple):
        return frozenset((value, (i + di, j + dj)) for value, (i, j) in patch)
    return frozenset((i + di, j + dj) for i, j in patch)


def normalize(
    patch: Patch
) -> Patch:
    """ moves upper left corner to origin """
    if len(patch) == 0:
        return patch
    return shift(patch, (-uppermost(patch), -leftmost(patch)))


def dneighbors(
    loc: IntegerTuple
) -> Indices:
    """ directly adjacent indices """
    return frozenset({(loc[0] - 1, loc[1]), (loc[0] + 1, loc[1]), (loc[0], loc[1] - 1), (loc[0], loc[1] + 1)})


def ineighbors(
    loc: IntegerTuple
) -> Indices:
    """ diagonally adjacent indices """
    return frozenset({(loc[0] - 1, loc[1] - 1), (loc[0] - 1, loc[1] + 1), (loc[0] + 1, loc[1] - 1), (loc[0] + 1, loc[1] + 1)})


def neighbors(
    loc: IntegerTuple
) -> Indices:
    """ adjacent indices """
    return dneighbors(loc) | ineighbors(loc)


def objects(
    grid: Grid,
    univalued: Boolean,
    diagonal: Boolean,
    without_bg: Boolean
) -> Objects:
    """ objects occurring on the grid """
    bg = mostcolor(grid) if without_bg else None
    objs = set()
    occupied = set()
    h, w = len(grid), len(grid[0])
    unvisited = asindices(grid)
    diagfun = neighbors if diagonal else dneighbors
    for loc in unvisited:
        if loc in occupied:
            continue
        val = grid[loc[0]][loc[1]]
        if val == bg:
            continue
        obj = {(val, loc)}
        cands = {loc}
        while len(cands) > 0:
            neighborhood = set()
            for cand in cands:
                v = grid[cand[0]][cand[1]]
                if (val == v) if univalued else (v != bg):
                    obj.add((v, cand))
                    occupied.add(cand)
                    neighborhood |= {
                        (i, j) for i, j in diagfun(cand) if 0 <= i < h and 0 <= j < w
                    }
            cands = neighborhood - occupied
        objs.add(frozenset(obj))
    return frozenset(objs)


def objects_with_explicit_bg(
    grid: list[list[int]],
    univalued: bool,
    diagonal: bool,
    skip_color: int
):
    """
    Similar to your objects(...) DSL function but
    uses skip_color as the background to skip.

    - If univalued=True: unify only same-color pixels that are != skip_color.
    - If univalued=False: unify all pixels except skip_color.
    - If diagonal=True: 8-connected adjacency. Else 4-connected adjacency.
    """
    h = len(grid)
    w = len(grid[0]) if h>0 else 0
    diagfun = neighbors if diagonal else dneighbors
    unvisited = asindices(grid)  # all (row,col)
    occupied = set()
    objs = set()

    for loc in unvisited:
        if loc in occupied:
            continue
        val = grid[loc[0]][loc[1]]
        # if univalued=True, we unify only pixels == val, skipping skip_color
        # if univalued=False, unify all colors != skip_color
        if univalued:
            if val == skip_color:
                # skip this pixel entirely
                continue
        else:
            # univalued=False, we unify everything != skip_color
            if val == skip_color:
                continue

        # BFS or DFS
        obj = {(val, loc)}
        cands = {loc}
        while cands:
            neighborset = set()
            for cand in cands:
                cval = grid[cand[0]][cand[1]]
                if univalued:
                    # unify if cval == val (and != skip_color)
                    if cval == val and cval != skip_color:
                        obj.add((cval, cand))
                        occupied.add(cand)
                        for npos in diagfun(cand):
                            if 0<=npos[0]<h and 0<=npos[1]<w:
                                if npos not in occupied:
                                    neighborset.add(npos)
                else:
                    # unify if cval != skip_color
                    if cval != skip_color:
                        obj.add((cval, cand))
                        occupied.add(cand)
                        for npos in diagfun(cand):
                            if 0<=npos[0]<h and 0<=npos[1]<w:
                                if npos not in occupied:
                                    neighborset.add(npos)
            cands = neighborset - occupied
        objs.add(frozenset(obj))

    return frozenset(objs)



def partition(
    grid: Grid
) -> Objects:
    """ each cell with the same value part of the same object """
    return frozenset(
        frozenset(
            (v, (i, j)) for i, r in enumerate(grid) for j, v in enumerate(r) if v == value
        ) for value in palette(grid)
    )


def fgpartition(
    grid: Grid
) -> Objects:
    """ each cell with the same value part of the same object without background """
    return frozenset(
        frozenset(
            (v, (i, j)) for i, r in enumerate(grid) for j, v in enumerate(r) if v == value
        ) for value in palette(grid) - {mostcolor(grid)}
    )


def uppermost(
    patch: Patch
) -> Integer:
    """ row index of uppermost occupied cell """
    return min(i for i, j in toindices(patch))


def lowermost(
    patch: Patch
) -> Integer:
    """ row index of lowermost occupied cell """
    return max(i for i, j in toindices(patch))


def leftmost(
    patch: Patch
) -> Integer:
    """ column index of leftmost occupied cell """
    return min(j for i, j in toindices(patch))


def rightmost(
    patch: Patch
) -> Integer:
    """ column index of rightmost occupied cell """
    return max(j for i, j in toindices(patch))


def square(
    piece: Piece
) -> Boolean:
    """ whether the piece forms a square """
    return len(piece) == len(piece[0]) if isinstance(piece, tuple) else height(piece) * width(piece) == len(piece) and height(piece) == width(piece)


def vline(
    patch: Patch
) -> Boolean:
    """ whether the piece forms a vertical line """
    return height(patch) == len(patch) and width(patch) == 1


def hline(
    patch: Patch
) -> Boolean:
    """ whether the piece forms a horizontal line """
    return width(patch) == len(patch) and height(patch) == 1


def hmatching(
    a: Patch,
    b: Patch
) -> Boolean:
    """ whether there exists a row for which both patches have cells """
    return len(set(i for i, j in toindices(a)) & set(i for i, j in toindices(b))) > 0


def vmatching(
    a: Patch,
    b: Patch
) -> Boolean:
    """ whether there exists a column for which both patches have cells """
    return len(set(j for i, j in toindices(a)) & set(j for i, j in toindices(b))) > 0


def manhattan(
    a: Patch,
    b: Patch
) -> Integer:
    """ closest manhattan distance between two patches """
    return min(abs(ai - bi) + abs(aj - bj) for ai, aj in toindices(a) for bi, bj in toindices(b))


def adjacent(
    a: Patch,
    b: Patch
) -> Boolean:
    """ whether two patches are adjacent """
    return manhattan(a, b) == 1


def bordering(
    patch: Patch,
    grid: Grid
) -> Boolean:
    """ whether a patch is adjacent to a grid border """
    return uppermost(patch) == 0 or leftmost(patch) == 0 or lowermost(patch) == len(grid) - 1 or rightmost(patch) == len(grid[0]) - 1


def centerofmass(
    patch: Patch
) -> IntegerTuple:
    """ center of mass """
    return tuple(map(lambda x: sum(x) // len(patch), zip(*toindices(patch))))


def palette(
    element: Element
) -> IntegerSet:
    """ colors occurring in object or grid """
    if isinstance(element, tuple):
        return frozenset({v for r in element for v in r})
    return frozenset({v for v, _ in element})


def numcolors(
    element: Element
) -> IntegerSet:
    """ number of colors occurring in object or grid """
    return len(palette(element))


def color(
    obj: Object
) -> Integer:
    """ color of object """
    return next(iter(obj))[0]


def toobject(
    patch: Patch,
    grid: Grid
) -> Object:
    """ object from patch and grid """
    h, w = len(grid), len(grid[0])
    return frozenset((grid[i][j], (i, j)) for i, j in toindices(patch) if 0 <= i < h and 0 <= j < w)


#def asobject(
#    grid: Grid
#) -> Object:
#    """ conversion of grid to object """
#    return frozenset((v, (i, j)) for i, r in enumerate(grid) for j, v in enumerate(r))

def asobject(grid):
    """
    Convert a grid into a set of (color, (row, col)) tuples.
    Ensures that color is always an integer.
    """
    obj = set()
    for i, row in enumerate(grid):
        for j, color in enumerate(row):
            if isinstance(color, tuple):
                print(f"🚨 Unexpected tuple color at ({i},{j}): {color}")  # Debugging
                color = color[0]  # Take only the first value (or handle it appropriately)
            obj.add((int(color), (i, j)))  # Ensure color is an int
    return frozenset(obj)

def rot90(
    grid: Grid
) -> Grid:
    """ quarter clockwise rotation """
    return tuple(row for row in zip(*grid[::-1]))


def rot180(
    grid: Grid
) -> Grid:
    """ half rotation """
    return tuple(tuple(row[::-1]) for row in grid[::-1])


def rot270(
    grid: Grid
) -> Grid:
    """ quarter anticlockwise rotation """
    return tuple(tuple(row[::-1]) for row in zip(*grid[::-1]))[::-1]


def hmirror(
    piece: Piece
) -> Piece:
    """ mirroring along horizontal """
    if isinstance(piece, tuple):
        return piece[::-1]
    d = ulcorner(piece)[0] + lrcorner(piece)[0]
    if isinstance(next(iter(piece))[1], tuple):
        return frozenset((v, (d - i, j)) for v, (i, j) in piece)
    return frozenset((d - i, j) for i, j in piece)


def vmirror(
    piece: Piece
) -> Piece:
    """ mirroring along vertical """
    if isinstance(piece, tuple):
        return tuple(row[::-1] for row in piece)
    d = ulcorner(piece)[1] + lrcorner(piece)[1]
    if isinstance(next(iter(piece))[1], tuple):
        return frozenset((v, (i, d - j)) for v, (i, j) in piece)
    return frozenset((i, d - j) for i, j in piece)


def dmirror(
    piece: Piece
) -> Piece:
    """ mirroring along diagonal """
    if isinstance(piece, tuple):
        return tuple(zip(*piece))
    a, b = ulcorner(piece)
    if isinstance(next(iter(piece))[1], tuple):
        return frozenset((v, (j - b + a, i - a + b)) for v, (i, j) in piece)
    return frozenset((j - b + a, i - a + b) for i, j in piece)


def cmirror(
    piece: Piece
) -> Piece:
    """ mirroring along counterdiagonal """
    if isinstance(piece, tuple):
        return tuple(zip(*(r[::-1] for r in piece[::-1])))
    return vmirror(dmirror(vmirror(piece)))


def fill(
    grid: Grid,
    value: Integer,
    patch: Patch
) -> Grid:
    """ fill value at indices """
    h, w = len(grid), len(grid[0])
    grid_filled = list(list(row) for row in grid)
    for i, j in toindices(patch):
        if 0 <= i < h and 0 <= j < w:
            grid_filled[i][j] = value
    return tuple(tuple(row) for row in grid_filled)


def paint(
    grid: Grid,
    obj: Object
) -> Grid:
    """ paint object to grid """
    h, w = len(grid), len(grid[0])
    grid_painted = list(list(row) for row in grid)
    for value, (i, j) in obj:
        if 0 <= i < h and 0 <= j < w:
            grid_painted[i][j] = value
    return tuple(tuple(row) for row in grid_painted)


def underfill(
    grid: Grid,
    value: Integer,
    patch: Patch
) -> Grid:
    """ fill value at indices that are background """
    h, w = len(grid), len(grid[0])
    bg = mostcolor(grid)
    g = list(list(r) for r in grid)
    for i, j in toindices(patch):
        if 0 <= i < h and 0 <= j < w:
            if g[i][j] == bg:
                g[i][j] = value
    return tuple(tuple(r) for r in g)


def underpaint(
    grid: Grid,
    obj: Object
) -> Grid:
    """ paint object to grid where there is background """
    h, w = len(grid), len(grid[0])
    bg = mostcolor(grid)
    g = list(list(r) for r in grid)
    for value, (i, j) in obj:
        if 0 <= i < h and 0 <= j < w:
            if g[i][j] == bg:
                g[i][j] = value
    return tuple(tuple(r) for r in g)


def hupscale(
    grid: Grid,
    factor: Integer
) -> Grid:
    """ upscale grid horizontally """
    g = tuple()
    for row in grid:
        r = tuple()
        for value in row:
            r = r + tuple(value for num in range(factor))
        g = g + (r,)
    return g


def vupscale(
    grid: Grid,
    factor: Integer
) -> Grid:
    """ upscale grid vertically """
    g = tuple()
    for row in grid:
        g = g + tuple(row for num in range(factor))
    return g


def upscale(
    element: Element,
    factor: Integer
) -> Element:
    """ upscale object or grid """
    if isinstance(element, tuple):
        g = tuple()
        for row in element:
            upscaled_row = tuple()
            for value in row:
                upscaled_row = upscaled_row + tuple(value for num in range(factor))
            g = g + tuple(upscaled_row for num in range(factor))
        return g
    else:
        if len(element) == 0:
            return frozenset()
        di_inv, dj_inv = ulcorner(element)
        di, dj = (-di_inv, -dj_inv)
        normed_obj = shift(element, (di, dj))
        o = set()
        for value, (i, j) in normed_obj:
            for io in range(factor):
                for jo in range(factor):
                    o.add((value, (i * factor + io, j * factor + jo)))
        return shift(frozenset(o), (di_inv, dj_inv))


def downscale(
    grid: Grid,
    factor: Integer
) -> Grid:
    """ downscale grid """
    h, w = len(grid), len(grid[0])
    g = tuple()
    for i in range(h):
        r = tuple()
        for j in range(w):
            if j % factor == 0:
                r = r + (grid[i][j],)
        g = g + (r, )
    h = len(g)
    dsg = tuple()
    for i in range(h):
        if i % factor == 0:
            dsg = dsg + (g[i],)
    return dsg


def hconcat(
    a: Grid,
    b: Grid
) -> Grid:
    """ concatenate two grids horizontally """
    return tuple(i + j for i, j in zip(a, b))


def vconcat(
    a: Grid,
    b: Grid
) -> Grid:
    """ concatenate two grids vertically """
    return a + b


def subgrid(
    patch: Patch,
    grid: Grid
) -> Grid:
    """ smallest subgrid containing object """
    return crop(grid, ulcorner(patch), shape(patch))


def hsplit(
    grid: Grid,
    n: Integer
) -> Tuple:
    """ split grid horizontally """
    h, w = len(grid), len(grid[0]) // n
    offset = len(grid[0]) % n != 0
    return tuple(crop(grid, (0, w * i + i * offset), (h, w)) for i in range(n))


def vsplit(
    grid: Grid,
    n: Integer
) -> Tuple:
    """ split grid vertically """
    h, w = len(grid) // n, len(grid[0])
    offset = len(grid) % n != 0
    return tuple(crop(grid, (h * i + i * offset, 0), (h, w)) for i in range(n))


def cellwise(
    a: Grid,
    b: Grid,
    fallback: Integer
) -> Grid:
    """ cellwise match of two grids """
    h, w = len(a), len(a[0])
    resulting_grid = tuple()
    for i in range(h):
        row = tuple()
        for j in range(w):
            a_value = a[i][j]
            value = a_value if a_value == b[i][j] else fallback
            row = row + (value,)
        resulting_grid = resulting_grid + (row, )
    return resulting_grid


def replace(
    grid: Grid,
    replacee: Integer,
    replacer: Integer
) -> Grid:
    """ color substitution """
    return tuple(tuple(replacer if v == replacee else v for v in r) for r in grid)


def switch(
    grid: Grid,
    a: Integer,
    b: Integer
) -> Grid:
    """ color switching """
    return tuple(tuple(v if (v != a and v != b) else {a: b, b: a}[v] for v in r) for r in grid)


def center(
    patch: Patch
) -> IntegerTuple:
    """ center of the patch """
    return (uppermost(patch) + height(patch) // 2, leftmost(patch) + width(patch) // 2)


def position(
    a: Patch,
    b: Patch
) -> IntegerTuple:
    """ relative position between two patches """
    ia, ja = center(toindices(a))
    ib, jb = center(toindices(b))
    if ia == ib:
        return (0, 1 if ja < jb else -1)
    elif ja == jb:
        return (1 if ia < ib else -1, 0)
    elif ia < ib:
        return (1, 1 if ja < jb else -1)
    elif ia > ib:
        return (-1, 1 if ja < jb else -1)


def index(
    grid: Grid,
    loc: IntegerTuple
) -> Integer:
    """ color at location """
    i, j = loc
    h, w = len(grid), len(grid[0])
    if not (0 <= i < h and 0 <= j < w):
        return None
    return grid[loc[0]][loc[1]]


def canvas(
    value: Integer,
    dimensions: IntegerTuple
) -> Grid:
    """ grid construction """
    return tuple(tuple(value for j in range(dimensions[1])) for i in range(dimensions[0]))


def corners(
    patch: Patch
) -> Indices:
    """ indices of corners """
    return frozenset({ulcorner(patch), urcorner(patch), llcorner(patch), lrcorner(patch)})


def connect(
    a: IntegerTuple,
    b: IntegerTuple
) -> Indices:
    """ line between two points """
    ai, aj = a
    bi, bj = b
    si = min(ai, bi)
    ei = max(ai, bi) + 1
    sj = min(aj, bj)
    ej = max(aj, bj) + 1
    if ai == bi:
        return frozenset((ai, j) for j in range(sj, ej))
    elif aj == bj:
        return frozenset((i, aj) for i in range(si, ei))
    elif bi - ai == bj - aj:
        return frozenset((i, j) for i, j in zip(range(si, ei), range(sj, ej)))
    elif bi - ai == aj - bj:
        return frozenset((i, j) for i, j in zip(range(si, ei), range(ej - 1, sj - 1, -1)))
    return frozenset()


def cover(
    grid: Grid,
    patch: Patch
) -> Grid:
    """ remove object from grid """
    return fill(grid, mostcolor(grid), toindices(patch))


def trim(
    grid: Grid
) -> Grid:
    """ trim border of grid """
    return tuple(r[1:-1] for r in grid[1:-1])


def move(
    grid: Grid,
    obj: Object,
    offset: IntegerTuple
) -> Grid:
    """ move object on grid """
    return paint(cover(grid, obj), shift(obj, offset))


def tophalf(
    grid: Grid
) -> Grid:
    """ upper half of grid """
    return grid[:len(grid) // 2]


def bottomhalf(
    grid: Grid
) -> Grid:
    """ lower half of grid """
    return grid[len(grid) // 2 + len(grid) % 2:]


def lefthalf(
    grid: Grid
) -> Grid:
    """ left half of grid """
    return rot270(tophalf(rot90(grid)))


def righthalf(
    grid: Grid
) -> Grid:
    """ right half of grid """
    return rot270(bottomhalf(rot90(grid)))


def vfrontier(
    location: IntegerTuple
) -> Indices:
    """ vertical frontier """
    return frozenset((i, location[1]) for i in range(30))


def hfrontier(
    location: IntegerTuple
) -> Indices:
    """ horizontal frontier """
    return frozenset((location[0], j) for j in range(30))


def backdrop(
    patch: Patch
) -> Indices:
    """ indices in bounding box of patch """
    if len(patch) == 0:
        return frozenset({})
    indices = toindices(patch)
    si, sj = ulcorner(indices)
    ei, ej = lrcorner(patch)
    return frozenset((i, j) for i in range(si, ei + 1) for j in range(sj, ej + 1))


def delta(
    patch: Patch
) -> Indices:
    """ indices in bounding box but not part of patch """
    if len(patch) == 0:
        return frozenset({})
    return backdrop(patch) - toindices(patch)


def gravitate(
    source: Patch,
    destination: Patch
) -> IntegerTuple:
    """ direction to move source until adjacent to destination """
    si, sj = center(source)
    di, dj = center(destination)
    i, j = 0, 0
    if vmatching(source, destination):
        i = 1 if si < di else -1
    else:
        j = 1 if sj < dj else -1
    gi, gj = i, j
    c = 0
    while not adjacent(source, destination) and c < 42:
        c += 1
        gi += i
        gj += j
        source = shift(source, (i, j))
    return (gi - i, gj - j)


def inbox(
    patch: Patch
) -> Indices:
    """ inbox for patch """
    ai, aj = uppermost(patch) + 1, leftmost(patch) + 1
    bi, bj = lowermost(patch) - 1, rightmost(patch) - 1
    si, sj = min(ai, bi), min(aj, bj)
    ei, ej = max(ai, bi), max(aj, bj)
    vlines = {(i, sj) for i in range(si, ei + 1)} | {(i, ej) for i in range(si, ei + 1)}
    hlines = {(si, j) for j in range(sj, ej + 1)} | {(ei, j) for j in range(sj, ej + 1)}
    return frozenset(vlines | hlines)


def outbox(
    patch: Patch
) -> Indices:
    """ outbox for patch """
    ai, aj = uppermost(patch) - 1, leftmost(patch) - 1
    bi, bj = lowermost(patch) + 1, rightmost(patch) + 1
    si, sj = min(ai, bi), min(aj, bj)
    ei, ej = max(ai, bi), max(aj, bj)
    vlines = {(i, sj) for i in range(si, ei + 1)} | {(i, ej) for i in range(si, ei + 1)}
    hlines = {(si, j) for j in range(sj, ej + 1)} | {(ei, j) for j in range(sj, ej + 1)}
    return frozenset(vlines | hlines)


def box(
    patch: Patch
) -> Indices:
    """ outline of patch """
    if len(patch) == 0:
        return patch
    ai, aj = ulcorner(patch)
    bi, bj = lrcorner(patch)
    si, sj = min(ai, bi), min(aj, bj)
    ei, ej = max(ai, bi), max(aj, bj)
    vlines = {(i, sj) for i in range(si, ei + 1)} | {(i, ej) for i in range(si, ei + 1)}
    hlines = {(si, j) for j in range(sj, ej + 1)} | {(ei, j) for j in range(sj, ej + 1)}
    return frozenset(vlines | hlines)


def shoot(
    start: IntegerTuple,
    direction: IntegerTuple
) -> Indices:
    """ line from starting point and direction """
    return connect(start, (start[0] + 42 * direction[0], start[1] + 42 * direction[1]))


def occurrences(
    grid: Grid,
    obj: Object
) -> Indices:
    """ locations of occurrences of object in grid """
    occs = set()
    normed = normalize(obj)
    h, w = len(grid), len(grid[0])
    oh, ow = shape(obj)
    h2, w2 = h - oh + 1, w - ow + 1
    for i in range(h2):
        for j in range(w2):
            occurs = True
            for v, (a, b) in shift(normed, (i, j)):
                if not (0 <= a < h and 0 <= b < w and grid[a][b] == v):
                    occurs = False
                    break
            if occurs:
                occs.add((i, j))
    return frozenset(occs)


def frontiers(
    grid: Grid
) -> Objects:
    """ set of frontiers """
    h, w = len(grid), len(grid[0])
    row_indices = tuple(i for i, r in enumerate(grid) if len(set(r)) == 1)
    column_indices = tuple(j for j, c in enumerate(dmirror(grid)) if len(set(c)) == 1)
    hfrontiers = frozenset({frozenset({(grid[i][j], (i, j)) for j in range(w)}) for i in row_indices})
    vfrontiers = frozenset({frozenset({(grid[i][j], (i, j)) for i in range(h)}) for j in column_indices})
    return hfrontiers | vfrontiers


def compress(
    grid: Grid
) -> Grid:
    """ removes frontiers from grid """
    ri = tuple(i for i, r in enumerate(grid) if len(set(r)) == 1)
    ci = tuple(j for j, c in enumerate(dmirror(grid)) if len(set(c)) == 1)
    return tuple(tuple(v for j, v in enumerate(r) if j not in ci) for i, r in enumerate(grid) if i not in ri)


def hperiod(
    obj: Object
) -> Integer:
    """ horizontal periodicity """
    normalized = normalize(obj)
    w = width(normalized)
    for p in range(1, w):
        offsetted = shift(normalized, (0, -p))
        pruned = frozenset({(c, (i, j)) for c, (i, j) in offsetted if j >= 0})
        if pruned.issubset(normalized):
            return p
    return w


def vperiod(
    obj: Object
) -> Integer:
    """ vertical periodicity """
    normalized = normalize(obj)
    h = height(normalized)
    for p in range(1, h):
        offsetted = shift(normalized, (-p, 0))
        pruned = frozenset({(c, (i, j)) for c, (i, j) in offsetted if i >= 0})
        if pruned.issubset(normalized):
            return p
    return h


# added

def zones(grid):
    return objects(grid, True, True, False)

def blocks(grid):
    return objects(grid, True, False, False)

def safe_divide(num: int, den: int) -> int:
    return branch(equality(den, 0), 0, divide(num, den))

def diff(a: int, b: int) -> int:
    return subtract(a, b)

def rank_colors_by_frequency_desc(grid):
    """
    Returns a list of (color, frequency) sorted by frequency descending.
    """
    from .dsl import palette, colorcount
    pal = palette(grid)  # frozenset of all colors
    freq_list = []
    for c in pal:
        freq_list.append((c, colorcount(grid, c)))
    # Sort by frequency descending; if tie, secondary sort by color
    freq_list.sort(key=lambda x: (x[1], x[0]), reverse=True)
    return freq_list

def top_two_and_bottom_two(grid):
    """
    Returns:
      (first_most_color, count_first_most,
       second_most_color, count_second_most,
       first_least_color, count_first_least,
       second_least_color, count_second_least)
    Safely handles edge cases (1 or 2 total colors).
    """
    freq_list = rank_colors_by_frequency_desc(grid)
    if not freq_list:
        # No colors at all? Edge case if grid has no cells.
        return (None, 0, None, 0, None, 0, None, 0)

    # First-most
    fm_color, fm_count = freq_list[0]

    if len(freq_list) == 1:
        # only one color
        return (fm_color, fm_count,
                None, 0,            # second-most doesn't exist
                fm_color, fm_count, # first-least is the same as most
                None, 0)            # second-least doesn't exist

    # Second-most
    sm_color, sm_count = freq_list[1]

    # For least colors, we look at the bottom of freq_list
    fl_color, fl_count = freq_list[-1]
    if len(freq_list) == 2:
        # exactly two colors
        return (fm_color, fm_count,
                sm_color, sm_count,
                fl_color, fl_count,  # the second color is also the least
                None, 0)             # no second-least
    # Otherwise, we have >= 3 colors
    sl_color, sl_count = freq_list[-2]

    return (fm_color, fm_count,
            sm_color, sm_count,
            fl_color, fl_count,
            sl_color, sl_count)

def block_color_touching_all_borders(grid):
    """
    Returns the color of the first block whose bounding box spans
    the full height and width of the grid. If no such block exists,
    returns None.
    """
    h = height(grid)
    w = width(grid)

    # 'blocks(grid)' is already defined in your DSL
    all_blocks = blocks(grid)

    for b in all_blocks:
        # shape(b) => (height_of_b, width_of_b) [bounding box dimensions]
        if shape(b) == (h, w):
            # We found a block that touches all four borders of the grid
            return color(b)  # color(...) is a DSL function returning that block's color.

    # If none matched
    return None

def middle_split_line_color(grid):
    """
    Returns the color (integer) of any "middle split line" blocks, if:
      - The block's bounding box is either:
        (grid_height x 1) with x in (0, grid_width-1), or
        (1 x grid_width) with y in (0, grid_height-1).
      - And all such blocks have the same color.
    Otherwise returns None.
    """
    grid_h = height(grid)
    grid_w = width(grid)

    line_blocks = []
    all_blocks = blocks(grid)  # univalued blocks

    for b in all_blocks:
        bh, bw = shape(b)  # bounding box (height_of_block, width_of_block)
        t = uppermost(b)  # row index of topmost cell
        l = leftmost(b)  # column index of leftmost cell

        # Check two conditions:

        # 1) Vertical line in the middle:
        #    shape(b) == (grid_h, 1)  AND  0 < leftmost(b) < grid_w-1
        if bh == grid_h and bw == 1:
            # check that its x/column is strictly between left and right
            if 0 < l < (grid_w - 1):
                line_blocks.append(b)
                continue

        # 2) Horizontal line in the middle:
        #    shape(b) == (1, grid_w)  AND  0 < topmost(b) < grid_h-1
        if bh == 1 and bw == grid_w:
            # check that its y/row is strictly between top and bottom
            if 0 < t < (grid_h - 1):
                line_blocks.append(b)
                continue

    # If no blocks match, return None
    if not line_blocks:
        return None

    # All blocks are univalued, so each has exactly one color
    colors = {color(b) for b in line_blocks}

    # If exactly one distinct color among them, return it
    if len(colors) == 1:
        return colors.pop()
    else:
        # More than one distinct color => None
        return None

def extract_shape(obj):
    """
    Returns a frozenset of (row,col) representing the 'shape' of an object
    after normalizing so its top-left cell is at (0,0).
    Ignores color.
    """
    coords = toindices(obj)  # DSL call -> returns all (r,c) in this patch/object
    if not coords:
        return frozenset()
    min_r = min(r for r, c in coords)
    min_c = min(c for r, c in coords)
    # shift so that top-left corner is at (0,0)
    shifted = frozenset((r - min_r, c - min_c) for (r, c) in coords)
    return shifted

def count_unique_shapes(objects_set):
    """
    Given a set of objects (blocks or zones),
    return how many unique shapes they have (as defined by extract_shape).
    """
    shapes = set()
    for obj in objects_set:
        shape_signature = extract_shape(obj)
        shapes.add(shape_signature)
    return len(shapes)

def is_rectangle(obj):
    """
    A block is a rectangle if bounding box area == number of cells.
    shape(obj) -> (bh, bw)
    len(obj)   -> number of cells in that object
    """
    bh, bw = shape(obj)
    return (bh * bw) == len(obj)

def is_square(obj):
    """
    A block is a square if it's a rectangle whose height == width.
    """
    bh, bw = shape(obj)
    # check the bounding box area = number of cells (rectangle) AND bh == bw
    return ((bh * bw) == len(obj)) and (bh == bw)

def is_straight_line(obj):
    """
    A block is a 'straight line' if it forms a 1-row or 1-column rectangle.
    i.e., bounding box area == number of cells, and either bh=1 or bw=1.
    """
    bh, bw = shape(obj)
    if (bh * bw) == len(obj) and (bh == 1 or bw == 1):
        return True
    return False

def positions_of(obj):
    """
    Returns a frozenset of (row,col) positions occupied by 'obj'.
    'obj' is typically a frozenset of (color,(r,c)).
    'toindices(obj)' returns a frozenset of (r,c).
    """
    return toindices(obj)

def color_of(obj):
    """
    Returns the single color of a univalued block or zone.
    In your DSL, color(obj) does exactly that.
    """
    return color(obj)

def build_posset_to_color_map(objects_set):
    """
    For a collection of blocks (or zones), build a dict:
        positions -> color
    where positions is the entire set of occupant cells, e.g. frozenset((r,c)).
    """
    mapping = {}
    for o in objects_set:
        pos_set = positions_of(o)
        c = color_of(o)
        mapping[pos_set] = c
    return mapping

def compare_same_vs_recolored(input_objects, output_objects):
    """
    For each object in 'input_objects', tries to find an object in 'output_objects'
    with the exact same occupant cell set (same shape, same location).
    If found:
      - If colors match, it's "same."
      - If colors differ, it's "recolored."
    Returns (count_same, count_recolored).
    """
    out_map = build_posset_to_color_map(output_objects)

    count_same = 0
    count_recolored = 0

    for iobj in input_objects:
        i_pos = positions_of(iobj)   # full set of occupant cells
        i_col = color_of(iobj)
        if i_pos in out_map:
            o_col = out_map[i_pos]
            if i_col == o_col:
                count_same += 1
            else:
                count_recolored += 1
        # else: no object in output has the same occupant cells -> no match
    return (count_same, count_recolored)

def count_blocks_touching_border(grid):
    """
    Return how many blocks (univalued objects) in 'grid'
    touch the grid border, i.e. at least one cell on the boundary.
    """
    all_blocks = blocks(grid)  # from your DSL
    return sum(1 for b in all_blocks if bordering(b, grid))

def convert_to_tuple_of_tuples(grid):
    return tuple(tuple(row) for row in grid)

def has_2x2_square(obj):
    """
    Check if the object contains at least one 2x2 square of pixels.
    A 2x2 square consists of four connected pixels.
    """
    pixels = toindices(obj)
    for r, c in pixels:
        if {(r, c), (r, c + 1), (r + 1, c), (r + 1, c + 1)}.issubset(pixels):
            return True  # Found a 2x2 square
    return False

def has_t_shape(obj):
    """
    Check if the object contains at least one T-shaped structure in any rotation.
    A T-shape consists of 4 pixels forming:
    - A horizontal line with a center pixel below
    - Or a vertical line with a center pixel to the side
    """
    pixels = toindices(obj)
    for r, c in pixels:
        t_shapes = [
            {(r, c), (r, c - 1), (r, c + 1), (r + 1, c)},  # T-shape pointing down
            {(r, c), (r, c - 1), (r, c + 1), (r - 1, c)},  # T-shape pointing up
            {(r, c), (r - 1, c), (r + 1, c), (r, c - 1)},  # T-shape pointing left
            {(r, c), (r - 1, c), (r + 1, c), (r, c + 1)},  # T-shape pointing right
        ]
        if any(t.issubset(pixels) for t in t_shapes):
            return True  # Found a T-shape
    return False

def is_object_path(obj):
    """
    Determine if the object is a path:
    - Must be a **block** (not a zone)
    - Must **not** contain a 2x2 square
    - Must have **at least 2 pixels**
    """
    return len(toindices(obj)) >= 2 and not has_2x2_square(obj)

def is_object_tree(obj):
    """
    Determine if the object is a tree:
    - Must be a path (`isPath=True`)
    - Must contain at least one T-shape
    """
    return is_object_path(obj) and has_t_shape(obj)

def compute_pixel_perimeter(obj):
    """
    Computes the perimeter of an object by summing all exposed pixel edges.
    Each pixel can contribute up to 4 edges if fully isolated.
    If a side of the pixel touches another pixel in the object, that edge is not counted.
    """
    perimeter = 0
    pixels = toindices(obj)

    for r, c in pixels:
        # Check all 4 sides and count only the exposed edges
        if (r - 1, c) not in pixels:  # Top edge
            perimeter += 1
        if (r + 1, c) not in pixels:  # Bottom edge
            perimeter += 1
        if (r, c - 1) not in pixels:  # Left edge
            perimeter += 1
        if (r, c + 1) not in pixels:  # Right edge
            perimeter += 1

    return perimeter

# Helper function to check if a component touches the border of a grid of size (grid_height x grid_width)
def touches_border(component, grid_height, grid_width):
    # Each component is a frozenset of (value, (i, j)) pairs.
    # If any cell lies on the border (i==0, i==grid_height-1, j==0, or j==grid_width-1),
    # then the component touches the border.
    for _, (i, j) in component:
        if i == 0 or i == grid_height - 1 or j == 0 or j == grid_width - 1:
            return True
    return False

PARTIALLY_MAX = 4

def count_exactly_align_horizontally(current, objects):
    """
    Count objects that have exactly the same vertical interval
    (minY and maxY) as the current object.
    """
    return sum(
        1 for o in objects
        if o["minY"] == current["minY"] and o["maxY"] == current["maxY"]
    )

def count_exactly_align_vertically(current, objects):
    """
    Count objects that have exactly the same horizontal interval
    (minX and maxX) as the current object.
    """
    return sum(
        1 for o in objects
        if o["minX"] == current["minX"] and o["maxX"] == current["maxX"]
    )

def build_align_data(obj):
    return {
        "minY": uppermost(obj),
        "maxY": lowermost(obj) + 1,  # add 1 so that a one-cell object spans 1 unit
        "minX": leftmost(obj),
        "maxX": rightmost(obj) + 1,
        "color": color(obj)
    }

def count_at_top_left(current, candidates):
    return sum(
        1 for o in candidates
        if o["maxY"] <= current["minY"] and o["maxX"] <= current["minX"]
    )

def count_at_top(current, candidates):
    return sum(
        1 for o in candidates
        if o["maxY"] <= current["minY"]
           and o["minX"] < current["maxX"]
           and o["maxX"] > current["minX"]
    )

def count_at_top_right(current, candidates):
    return sum(
        1 for o in candidates
        if o["maxY"] <= current["minY"] and o["minX"] >= current["maxX"]
    )

def count_at_left(current, candidates):
    return sum(
        1 for o in candidates
        if o["maxX"] <= current["minX"]
           and o["minY"] < current["maxY"]
           and o["maxY"] > current["minY"]
    )

def count_at_right(current, candidates):
    return sum(
        1 for o in candidates
        if o["minX"] >= current["maxX"]
           and o["minY"] < current["maxY"]
           and o["maxY"] > current["minY"]
    )

def count_at_bottom_left(current, candidates):
    return sum(
        1 for o in candidates
        if o["minY"] >= current["maxY"] and o["maxX"] <= current["minX"]
    )

def count_at_bottom(current, candidates):
    return sum(
        1 for o in candidates
        if o["minY"] >= current["maxY"]
           and o["minX"] < current["maxX"]
           and o["maxX"] > current["minX"]
    )

def count_at_bottom_right(current, candidates):
    return sum(
        1 for o in candidates
        if o["minY"] >= current["maxY"] and o["minX"] >= current["maxX"]
    )

def rot90Shape(shape):
    rotated = {(c, -r) for r, c in shape}
    min_r = min(r for r, c in rotated)
    min_c = min(c for r, c in rotated)
    return frozenset((r - min_r, c - min_c) for r, c in rotated)

def rot180Shape(shape):
    rotated = {(-r, -c) for r, c in shape}
    min_r = min(r for r, c in rotated)
    min_c = min(c for r, c in rotated)
    return frozenset((r - min_r, c - min_c) for r, c in rotated)

def rot270Shape(shape):
    rotated = {(-c, r) for r, c in shape}
    min_r = min(r for r, c in rotated)
    min_c = min(c for r, c in rotated)
    return frozenset((r - min_r, c - min_c) for r, c in rotated)

def vmirrorShape(shape):
    mirrored = {(-r, c) for r, c in shape}
    min_r = min(r for r, c in mirrored)
    min_c = min(c for r, c in mirrored)
    return frozenset((r - min_r, c - min_c) for r, c in mirrored)

def hmirrorShape(shape):
    mirrored = {(r, -c) for r, c in shape}
    min_r = min(r for r, c in mirrored)
    min_c = min(c for r, c in mirrored)
    return frozenset((r - min_r, c - min_c) for r, c in mirrored)

def object_to_grid(obj):
    """
    Given an object (frozenset of (color, (row, col)) pairs), compute the bounding box
    and return a grid (tuple of tuples of ints) with background 0.
    """
    if not obj:
        return tuple()
    indices = [pos for _, pos in obj]
    min_row = min(i for i, j in indices)
    max_row = max(i for i, j in indices)
    min_col = min(j for i, j in indices)
    max_col = max(j for i, j in indices)
    rows = max_row - min_row + 1
    cols = max_col - min_col + 1
    grid = [[0]*cols for _ in range(rows)]
    for color, (i, j) in obj:
        grid[i - min_row][j - min_col] = color
    return tuple(tuple(row) for row in grid)

def safe_to_grid(data):
    """
    If data is a raw grid (list/tuple of lists/tuples of ints), convert it to a tuple-of-tuples.
    If it is already an object (frozenset of (color, (row, col)) pairs),
    then convert it to a grid using object_to_grid.
    """
    if isinstance(data, frozenset):
        return object_to_grid(data)
    elif isinstance(data, (list, tuple)):
        # Check first element: if it’s a list/tuple of ints, assume raw grid.
        if data and isinstance(data[0], (list, tuple)):
            # also check the first cell
            first_cell = data[0][0]
            if isinstance(first_cell, int):
                return tuple(tuple(row) for row in data)
        # Otherwise, assume it is already in object form
        return data
    else:
        return data

def safe_asobject(data):
    """
    If data is already an object (frozenset of (color, (row, col)) pairs), return it;
    otherwise, convert the raw grid into an object.
    """
    if isinstance(data, frozenset):
        return data
    else:
        return asobject(data)  # asobject is your DSL function

# Now, define grid-based transformation functions that operate on raw grids:
def rot90_grid(grid):
    """Rotate grid 90° clockwise."""
    return tuple(tuple(row) for row in zip(*grid[::-1]))

def rot180_grid(grid):
    """Rotate grid 180°."""
    return tuple(row[::-1] for row in grid[::-1])

def rot270_grid(grid):
    """Rotate grid 270° clockwise."""
    return tuple(tuple(row) for row in zip(*grid))[::-1]

def hmirror_grid(grid):
    """Mirror grid horizontally."""
    return tuple(row[::-1] for row in grid)

def vmirror_grid(grid):
    """Mirror grid vertically."""
    return grid[::-1]

# Then, define sprite-specific transformation functions that always work on a raw grid:
def rot90Sprite(sprite_data):
    grid = safe_to_grid(sprite_data)
    return safe_asobject(rot90_grid(grid))

def rot180Sprite(sprite_data):
    grid = safe_to_grid(sprite_data)
    return safe_asobject(rot180_grid(grid))

def rot270Sprite(sprite_data):
    grid = safe_to_grid(sprite_data)
    return safe_asobject(rot270_grid(grid))

def hmirrorSprite(sprite_data):
    grid = safe_to_grid(sprite_data)
    return safe_asobject(hmirror_grid(grid))

def vmirrorSprite(sprite_data):
    grid = safe_to_grid(sprite_data)
    return safe_asobject(vmirror_grid(grid))

# And update canonical_sprite_representation so it works on either raw grids or objects:
def canonical_sprite_representation(sprite_data):
    """
    Convert a sprite (raw grid or object) into a canonical JSON string representation.
    """
    obj = safe_asobject(sprite_data)
    # Now, obj is a frozenset of (color, (row, col)) pairs where color is an int.
    sorted_list = sorted(obj, key=lambda x: (x[0], x[1][0], x[1][1]))
    return json.dumps(sorted_list)

def norm_coord(x):
    while isinstance(x, tuple):
        x = x[0]
    return x


#!/usr/bin/env python
# coding: utf-8

"""
Utilities for generating perfect hash functions for integer keys.

This module implements the first fit decreasing method, described in
Gettys01_. It is **not** guaranteed to generate a *minimal* perfect hash,
though by no means is it impossible. See for example:

>>> phash = hash_parameters('+-<>[].,', to_int=ord)
>>> len(phash.slots)
8
>>> phash.slots
('+', ',', '-', '.', '<', '[', '>', ']')

.. _Gettys01: http://www.drdobbs.com/architecture-and-design/generating-perfect-hash-functions/184404506

"""

import math
import collections
import heapq

__all__ = ['hash_parameters', 'make_hash', 'make_dict']


HashInfo = collections.namedtuple('HashInfo', 't slots r offset to_int')


__identity = lambda x: x


def hash_parameters(keys, minimize=True, to_int=None):
    """
    Calculates the parameters for a perfect hash. The result is returned as a
    HashInfo tuple which has the following fields:

    t
       The "table parameter". This is the minimum side length of the table
       used to create the hash. In practice, t**2 is the maximum size of the
       output hash.
    slots
       The original inputs mapped to a vector. This is the hash function.
    r
       The displacement vector. This is the displacement of the given row in
       the result vector. To find a given value, use ``x + r[y]``.
    offset
       The amount by which to offset all values (once converted to ints)
    to_int
       A function that converts the input to an int (if given).

    Keyword parameters:

    ``minimize``
        Whether or not offset all integer keys internally by the minimum
        value. This typically results in smaller output.
    ``to_int``
        A callable that converts the input keys to ints. If not specified, all
        keys should be given as ints.


    >>> hash_parameters([1, 5, 7], minimize=False)
    HashInfo(t=3, slots=(1, 5, 7), r=(-1, -1, 1), offset=0, to_int=None)

    >>> hash_parameters([1, 5, 7])
    HashInfo(t=3, slots=(1, 5, 7), r=(0, 0, 2), offset=-1, to_int=None)

    >>> l = (0, 3, 4, 7 ,10, 13, 15, 18, 19, 21, 22, 24, 26, 29, 30, 34)
    >>> phash = hash_parameters(l)
    >>> phash.slots
    (18, 19, 0, 21, 22, 3, 4, 24, 7, 26, 30, 10, 29, 13, 34, 15)
    """

    # If to_int is not assigned, simply use the identity function.
    if to_int is None:
        to_int = __identity

    key_to_original = {to_int(original): original for original in keys}

    # Create a set of all items to be hashed.
    items = key_to_original.keys()

    if minimize:
        offset = 0 - min(items)
        items = frozenset(x + offset for x in items)
    else:
        offset = 0

    # 1. Start with a square array (not stored) that is t units on each side.
    # Choose a t such that t * t >= max(S)
    t = choose_best_t(items)
    assert t * t >= max(items) and t * t >= len(items)

    # 2. Place each key K in the square at location (x,y), where
    # x = K mod t, y = K / t.
    row_queue = place_items_in_square(items, t)

    # 3. Arrange rows so that they'll fit into one row and generate a
    # displacement vector.
    final_row, displacement_vector = arrange_rows(row_queue, t)

    # Translate the internal keys to their original items.
    slots = tuple(key_to_original[item - offset] if item is not None else None
                  for item in final_row)

    # Return the parameters
    return HashInfo(
        t=t,
        slots=slots,
        r=displacement_vector,
        offset=offset,
        to_int=to_int if to_int is not __identity else None
    )


def choose_best_t(items):
    minimum_allowable = int(math.ceil(math.sqrt(max(items))))
    if minimum_allowable ** 2 < len(items):
        return len(items)
    else:
        return minimum_allowable


def place_items_in_square(items, t):
    """
    Returns a list of rows that are stored as a priority queue to be used
    with heapq functions.

    >>> place_items_in_square([1,5,7], 4)
    [(2, 1, [(1, 5), (3, 7)]), (3, 0, [(1, 1)])]
    >>> place_items_in_square([1,5,7], 3)
    [(2, 0, [(1, 1)]), (2, 1, [(2, 5)]), (2, 2, [(1, 7)])]
    """

    # A minheap (because that's all that heapq supports :/)
    # of the length of each row. Why this is important is because
    # we'll be popping the largest rows when figuring out row displacements.
    # Each item is a tuple of (t - |row|, y, [(xpos_1, item_1), ...]).
    # Until the call to heapq.heapify(), the rows are ordered in
    # increasing row number (y).
    rows = [(t, y, []) for y in xrange(t)]

    for item in items:
        # Calculate the cell the item should fall in.
        x = item % t
        y = item // t

        # Push the item to its corresponding row...
        inverse_length, _, row_contents = rows[y]
        heapq.heappush(row_contents, (x, item))

        # Ensure the heap key is kept intact.
        rows[y] = inverse_length - 1, y, row_contents

    assert all(inv_len == t - len(rows) for inv_len, _, rows in rows)

    heapq.heapify(rows)

    # Return only rows that are populated.
    return [row for row in rows if row[2]]


def arrange_rows(row_queue, t):
    """
    Takes a priority queue as generated by place_items_in_square().
    Arranges the items from its conceptual square to one list.
    Returns both the resultant vector, plus the displacement vector, to be
    used in the final output hash function.

    >>> rows = [(2, 1, [(0, 1), (1, 5)]), (3, 3, [(1, 7)])]
    >>> result, displacements = arrange_rows(rows, 4)
    >>> result
    (1, 5, 7)
    >>> displacements
    (None, 0, None, 1)

    >>> rows = [(1, 1, [(0, 1), (2, 7)]), (2, 2, [(1, 5)])]
    >>> result, displacements = arrange_rows(rows, 3)
    >>> result
    (1, 5, 7)
    >>> displacements
    (None, 0, 0)
    """

    # Create a set of all of the unoccupied columns.
    max_columns = t ** 2
    cols = ((x, True) for x in xrange(max_columns))
    unoccupied_columns = collections.OrderedDict(cols)

    # Create the resultant and displacement vectors.
    result = [None] * max_columns
    displacements = [None] * t

    while row_queue:
        # Get the next row to place.
        _inverse_length, y, row = heapq.heappop(row_queue)

        offset = find_first_fit(unoccupied_columns, row, max_columns)
        # Calculate the offset of the first item.
        first_item_x = row[0][0]

        displacements[y] = offset
        for x, item in row:
            actual_x = x + offset
            result[actual_x] = item
            del unoccupied_columns[actual_x]

    return tuple(trim_nones_from_right(result)), tuple(displacements)


def find_first_fit(unoccupied_columns, row, row_length):
    """
    Finds the first index that the row's items can fit.

    """
    for free_col in unoccupied_columns:
        # The offset is that such that the first item goes in the free column.
        first_item_x = row[0][0]
        offset = free_col - first_item_x
        if check_columns_fit(unoccupied_columns, row, offset, row_length):
            return offset

    raise ValueError("Row cannot bossily fit in %r: %r"
                     % (unoccupied_columns.keys(), row))


def check_columns_fit(unoccupied_columns, row, offset, row_length):
    """
    Checks if all the occupied columns in the row fit in the indices given by
    free columns.

    >>> check_columns_fit({0,1,2,3}, [(0, True), (2, True)], 0, 4)
    True
    >>> check_columns_fit({0,2,3}, [(2, True), (3, True)], 0, 4)
    True
    >>> check_columns_fit({}, [(2, True), (3, True)], 0, 4)
    False
    >>> check_columns_fit({0}, [(2, True)], 2, 4)
    True
    >>> check_columns_fit({0}, [(3, True)], 2, 4)
    False

    """
    for index, item in row:
        adjusted_index = (index + offset) % row_length

        # Check if the index is in the appropriate place.
        if adjusted_index not in unoccupied_columns:
            return False

    return True


def print_square(row_queue, t):
    """
    Prints a row queue as its conceptual square array.
    """
    occupied_rows = {y: row for _, y, row in row_queue}

    empty_row = ', '.join('...' for _ in xrange(t))
    for y in xrange(t):
        print '|',
        if y not in occupied_rows:
            print empty_row,
        else:
            row = dict(occupied_rows[y])
            all_cols = ('%3d' % row[x] if x in row else '...'
                        for x in xrange(t))
            print ', '.join(all_cols),

        print "|"


def trim_nones_from_right(xs):
    """
    Returns the list without all the Nones at the right end.

    >>> trim_nones_from_right([1, 2, None, 4, None, 5, None, None])
    [1, 2, None, 4, None, 5]

    """
    # Find the first element that does not contain none.
    for i, item in enumerate(reversed(xs)):
        if item is not None:
            break

    return xs[:-i]


def make_hash(keys, **kwargs):
    """
    Creates a perfect hash function from the given keys. For a description of
    the keyword arguments see :py:func:`hash_parameters`.

    >>> l = (0, 3, 4, 7 ,10, 13, 15, 18, 19, 21, 22, 24, 26, 29, 30, 34)
    >>> hf = make_hash(l)
    >>> hf(19)
    1
    >>> hash_parameters(l).slots[1]
    19
    """
    params = hash_parameters(keys, **kwargs)

    t = params.t
    r = params.r
    offset = params.offset
    to_int = params.to_int if params.to_int else __identity

    def perfect_hash(x):
        val = to_int(x) + offset
        x = val % t
        y = val / t
        return x + r[y]

    # Undocumented properties, but used in make_dict()...
    perfect_hash.length = len(params.slots)
    perfect_hash.slots = params.slots

    return perfect_hash


def make_dict(name, keys, **kwargs):
    """
    Creates a dictionary-like mapping class that uses perfect hashing.
    ``name`` is the proper class name of the returned class. See
    ``hash_parameters()`` for documentation on all arguments after ``name``.

    >>> MyDict = make_dict('MyDict', '+-<>[],.', to_int=ord)
    >>> d = MyDict([('+', 1), ('-', 2)])
    >>> d[','] = 3
    >>> d
    MyDict([('+', 1), (',', 3), ('-', 2)])
    >>> del d['+']
    >>> del d['.']
    Traceback (most recent call last):
    ...
    KeyError: '.'
    >>> len(d)
    2
    """

    hash_func = make_hash(keys, **kwargs)

    # Returns array index or ra
    def index_or_key_error(key):
        index = hash_func(key)
        # Make sure the key is **exactly** the same.
        if key != hash_func.slots[index]:
            raise KeyError(key)
        return index

    def init(self, *args, **kwargs):
        self._arr = [None] * hash_func.length
        self._len = 0

        # Delegate iniaitlization to update provided by MutableMapping:
        self.update(*args, **kwargs)

    def getitem(self, key):
        index = index_or_key_error(key)
        if self._arr[index] is None:
            raise KeyError(key)
        return self._arr[index][1]

    def setitem(self, key, value):
        index = index_or_key_error(key)
        self._arr[index] = (key, value)

    def delitem(self, key):
        index = index_or_key_error(key)
        if self._arr[index] is None:
            raise KeyError(key)
        self._arr[index] = None

    def dict_iter(self):
        return (pair[0] for pair in self._arr if pair is not None)

    def dict_len(self):
        # TODO: Make this O(1) using auxillary state?
        return sum(1 for _ in self)

    def dict_repr(self):
        arr_repr = (repr(pair) for pair in self._arr if pair is not None)
        return ''.join((name, '([', ', '.join(arr_repr), '])'))

    # Create a docstring that at least describes where the class came from...
    doc = """
        Dictionary-like object that uses perfect hashing. This class was
        generated by `%s.%s(%r, ...)`.
        """ % (__name__, make_dict.__name__, name)

    # Inheriting from MutableMapping gives us a whole whackload of methods for
    # free.
    bases = (collections.MutableMapping,)

    return type(name, bases, {
        '__init__': init,
        '__doc__': doc,

        '__getitem__': getitem,
        '__setitem__': setitem,
        '__delitem__': delitem,
        '__iter__': dict_iter,
        '__len__': dict_len,

        '__repr__': dict_repr,
    })


if __name__ == '__main__':
    # TODO: Make this main more useful.
    import doctest
    doctest.testmod(verbose=False)

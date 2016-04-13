from bitarray import bitarray


def deserialize(binary_data):
    return bitarray(binary_data)


def deserialize_filters(filters):
    res = []
    for i, f in enumerate(filters):
        ba = deserialize(f)
        res.append( (ba, i, ba.count()))

    return res


def serialize(ba):
    return ''.join(str(int(i)) for i in ba)



def serialize_filters(filters):
    return [
        serialize(f[0]) for f in filters
    ]

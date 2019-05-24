#AUTOGENERATED! DO NOT EDIT! File to edit: dev/02_data_pipeline.ipynb (unless otherwise specified).

__all__ = ['Transform', 'Pipeline', 'PipedList', 'TfmList']

from ..imports import *
from ..test import *
from ..core import *
from ..notebook.showdoc import show_doc

@docs
class Transform():
    "A function that `encodes` if `filt` matches, and optionally `decodes`, with an optional `setup`"
    order,filt = 0,None

    def __init__(self, encodes=None, **kwargs):
        if encodes is not None: self.encodes=encodes
        for k,v in kwargs.items(): setattr(self, k, v)

    @classmethod
    def create(cls, f, filt=None):
        "classmethod: Turn `f` into a `Transform` unless it already is one"
        return f if hasattr(f,'decode') or isinstance(f,Transform) else cls(f)

    def _filt_match(self, filt): return self.filt is None or self.filt==filt
    def __call__(self, o, filt=None, **kwargs): return self.encodes(o, **kwargs) if self._filt_match(filt) else o
    def __getitem__(self, x): return self(x)
    def decode  (self, o, filt=None, **kwargs): return self.decodes(o, **kwargs) if self._filt_match(filt) else o
    def __repr__(self): return str(self.encodes) if self.__class__==Transform else str(self.__class__)
    def decodes(self, o, *args, **kwargs): return o

    _docs=dict(__call__="Call `self.encodes` unless `filt` is passed and it doesn't match `self.filt`",
              decode="Call `self.decodes` unless `filt` is passed and it doesn't match `self.filt`",
              decodes="Override to implement custom decoding")

class Pipeline():
    "A pipeline of composed (for encode/decode) transforms, setup one at a time"
    def __init__(self, tfms):
        self.tfms = []
        self.add([Transform.create(t) for t in listify(tfms)])

    def add(self, tfms):
        "Call `setup` on all `tfms` and append them to this pipeline"
        for t in sorted(listify(tfms), key=lambda o: getattr(o, 'order', 0)):
            self.tfms.append(t)
            if hasattr(t, 'setup'): t.setup(self)

    def composed(self, x, rev=False, fname='__call__', **kwargs):
        "Compose `{fname}` of all `self.tfms` (reversed if `rev`) on `x`"
        tfms = reversed(self.tfms) if rev else self.tfms
        for f in tfms: x = opt_call(f, fname, x, **kwargs)
        return x

    def __call__(self, x, **kwargs): return self.composed(x, **kwargs)
    def __getitem__(self, x): return self(x)
    def decode(self, x, **kwargs): return self.composed(x, rev=True, fname='decode', **kwargs)
    def decode_at(self, idx): return self.decode(self[idx])
    def show_at(self, idx): return self.show(self[idx])
    def __repr__(self): return str(self.tfms)
    def delete(self, idx): del(self.tfms[idx])
    def remove(self, tfm): self.tfms.remove(tfm)

    def show(self, o, *args, **kwargs):
        "Find last transform that supports `show` and pass it decoded `o`"
        for t in reversed(self.tfms):
            o = getattr(t, 'decode', noop)(o)
            s = getattr(t, 'show', None)
            if s: return s(o, *args, **kwargs)

add_docs(
    Pipeline,
    __call__="Compose `__call__` of all `tfms` on `x`",
    decode="Compose `decode` of all `tfms` on `x`",
    decode_at="Decoded item at `idx`",
    show_at  ="Show item at `idx`",
    delete="Delete transform `idx` from pipeline",
    remove="Remove `tfm` from pipeline",
)

class PipedList(Pipeline):
    "A `Pipeline` of transforms applied to a collection of `items`"
    def __init__(self, items, tfms):
        self.items = ListContainer(items)
        super().__init__(tfms)

    def __getitem__(self, i):
        "Transformed item(s) at `i`"
        its = self.items[i]
        return its.mapped(self) if is_iter(i) else self(its)

    def __eq__(self, b): return all_equal(self, b)
    def __len__(self): return len(self.items)
    def __repr__(self): return f"{self.__class__.__name__}: {self.items}\ntfms - {self.tfms}"

class TfmList():
    def __init__(self, items, tfms): self.activ,self.tfms = None,[PipedList(items, t) for t in listify(tfms)]
    def __repr__(self): return f'TfmList({self.tfms})'

    def __getitem__(self, i):
        if self.activ is not None: return self.activ[i]
        return [t[i] for t in self.tfms]

    def decode(self, o, **kwargs): return [t.decode(p, **kwargs) for p,t in zip(o,self.tfms)]

    def setup(self, o):
        for tfm in self.tfms:
            self.activ = tfm
            tfm.setup(o)
        self.activ=None

    def show(self, o, ax=None, **kwargs):
        for p,t in zip(o,self.tfms): ax = t.show(p, ax=ax, **kwargs)

    xt,yt = add_props(lambda i,x:x.tfms[i])
#AUTOGENERATED! DO NOT EDIT! File to edit: dev/13_learner.ipynb (unless otherwise specified).

__all__ = ['CancelFitException', 'CancelEpochException', 'CancelTrainException', 'CancelValidException',
           'CancelBatchException', 'Callback', 'TrainEvalCallback', 'GatherPredsCallback', 'event', 'replacing_yield',
           'mk_metric', 'save_model', 'load_model', 'Learner', 'VerboseCallback', 'Metric', 'AvgMetric', 'AvgLoss',
           'AvgSmoothLoss', 'Recorder']

#Cell
from .test import *
from .data.all import *
from .optimizer import *

#Cell
class Callback(GetAttr):
    "Basic class handling tweaks of the training loop by changing a `Learner` in various events"
    _default,learn = 'learn',None
    def __repr__(self): return type(self).__name__

    def __call__(self, event_name):
        "Call `self.{event_name}` if it's defined"
        getattr(self, event_name, noop)()

    @property
    def name(self):
        "Name of the `Callback`, camel-cased and with '*Callback*' removed"
        return class2attr(self, 'Callback')

#Cell
class TrainEvalCallback(Callback):
    "`Callback` that tracks the number of iterations done and properly sets training/eval mode"
    def begin_fit(self):
        "Set the iter and epoch counters to 0, put the model and the right device"
        self.learn.train_iter,self.learn.pct_train = 0,0.
        self.model.to(self.dbunch.device)

    def after_batch(self):
        "Update the iter counter (in training mode)"
        if not self.training: return
        self.learn.pct_train += 1./(self.n_iter*self.n_epoch)
        self.learn.train_iter   += 1

    def begin_train(self):
        "Set the model in training mode"
        self.learn.pct_train=self.epoch/self.n_epoch
        self.model.train()
        self.learn.training=True

    def begin_validate(self):
        "Set the model in validation mode"
        self.model.eval()
        self.learn.training=False

#Cell
class GatherPredsCallback(Callback):
    "`Callback` that saves the predictions and targets, optionally `with_loss`"
    def __init__(self, with_input=False, with_loss=False): store_attr(self, "with_input,with_loss")

    def begin_batch(self):
        if self.with_input: self.inputs.append((to_detach(self.xb)))

    def begin_validate(self):
        "Initialize containers"
        self.preds,self.targets = [],[]
        if self.with_input: self.inputs=[]
        if self.with_loss: self.losses = []

    def after_batch(self):
        "Save predictions, targets and potentially losses"
        self.preds.append(to_detach(self.pred))
        self.targets.append(to_detach(self.yb))
        if self.with_loss:
            bs = find_bs(self.yb)
            loss = self.loss if self.loss.numel() == bs else self.loss.view(bs,-1).mean(1)
            self.losses.append(to_detach(loss))

#Cell
_ex_docs = dict(
    CancelFitException="Skip the rest of this batch and go to `after_batch`",
    CancelEpochException="Skip the rest of the training part of the epoch and go to `after_train`",
    CancelTrainException="Skip the rest of the validation part of the epoch and go to `after_validate`",
    CancelValidException="Skip the rest of this epoch and go to `after_epoch`",
    CancelBatchException="Interrupts training and go to `after_fit`")

for c,d in _ex_docs.items(): mk_class(c,sup=Exception,doc=d)

#Cell
_events = L.split('begin_fit begin_epoch begin_train begin_batch after_pred after_loss \
    after_backward after_step after_cancel_batch after_batch after_cancel_train \
    after_train begin_validate after_cancel_validate after_validate after_cancel_epoch \
    after_epoch after_cancel_fit after_fit')

mk_class('event', **_events.map_dict(),
         doc="All possible events as attributes to get tab-completion and typo-proofing")

_before_epoch = [event.begin_fit, event.begin_epoch]
_after_epoch  = [event.after_epoch, event.after_fit]

#Cell
defaults.lr = slice(3e-3)
defaults.wd = 1e-2
defaults.callbacks = [TrainEvalCallback]

#Cell
def replacing_yield(o, attr, val):
    "Context manager to temporarily replace an attribute"
    old = getattr(o,attr)
    try:     yield setattr(o,attr,val)
    finally: setattr(o,attr,old)

#Cell
def mk_metric(m):
    "Convert `m` to an `AvgMetric`, unless it's already a `Metric`"
    return m if isinstance(m, Metric) else AvgMetric(m)

#Cell
def save_model(file, model, opt, with_opt=True):
    "Save `model` to `file` along with `opt` (if available, and if `with_opt`)"
    if opt is None: with_opt=False
    state = get_model(model).state_dict()
    if with_opt: state = {'model': state, 'opt':opt.state_dict()}
    torch.save(state, file)

#Cell
def load_model(file, model, opt, with_opt=None, device=None, strict=True):
    "Load `model` from `file` along with `opt` (if available, and if `with_opt`)"
    if isinstance(device, int): device = torch.device('cuda', device)
    elif device is None: device = 'cpu'
    state = torch.load(file, map_location=device)
    hasopt = set(state)=={'model', 'opt'}
    model_state = state['model'] if hasopt else state
    get_model(model).load_state_dict(model_state, strict=strict)
    if hasopt and ifnone(with_opt,True):
        try: opt.load_state_dict(state['opt'])
        except:
            if with_opt: warn("Could not load the optimizer state.")
    elif with_opt: warn("Saved filed doesn't contain an optimizer state.")

#Cell
def _try_concat(o):
    try:
        return torch.cat(o)
    except:
        return sum([L(o_[i,:] for i in range_of(o_)) for o_ in o], L())

#Cell
class Learner():
    def __init__(self, dbunch, model, loss_func=None, opt_func=Adam, lr=defaults.lr, splitter=trainable_params, cbs=None,
                 cb_funcs=None, metrics=None, path=None, model_dir='models', wd_bn_bias=False, train_bn=True):
        store_attr(self, "dbunch,model,opt_func,lr,splitter,model_dir,wd_bn_bias,train_bn,metrics")
        self.training,self.logger,self.opt,self.cbs = False,print,None,L()
        #TODO: infer loss_func from data
        if loss_func is None:
            loss_func = getattr(dbunch.train_ds, 'loss_func', None)
            assert loss_func is not None, "Could not infer loss function from the data, please pass a loss function."
        self.loss_func = loss_func
        self.path = path if path is not None else getattr(dbunch, 'path', Path('.'))
        self.add_cbs(cbf() for cbf in L(defaults.callbacks)+L(cb_funcs))
        self.add_cbs(cbs)
        self.model.to(self.dbunch.device)

    @property
    def metrics(self): return self._metrics
    @metrics.setter
    def metrics(self,v): self._metrics = L(v).map(mk_metric)

    def add_cbs(self, cbs): L(cbs).map(self.add_cb)
    def remove_cbs(self, cbs): L(cbs).map(self.remove_cb)
    def add_cb(self, cb):
        old = getattr(self, cb.name, None)
        assert not old or isinstance(old, type(cb)), f"self.{cb.name} already registered"
        cb.learn = self
        setattr(self, cb.name, cb)
        self.cbs.append(cb)
        return self

    def remove_cb(self, cb):
        cb.learn = None
        if hasattr(self, cb.name): delattr(self, cb.name)
        if cb in self.cbs: self.cbs.remove(cb)

    @contextmanager
    def added_cbs(self, cbs):
        self.add_cbs(cbs)
        yield
        self.remove_cbs(cbs)

    def ordered_cbs(self, cb_func:str): return [cb for cb in sort_by_run(self.cbs) if hasattr(cb, cb_func)]

    def __call__(self, event_name): L(event_name).map(self._call_one)
    def _call_one(self, event_name):
        assert hasattr(event, event_name)
        [cb(event_name) for cb in sort_by_run(self.cbs)]

    def _bn_bias_state(self, with_bias): return bn_bias_params(self.model, with_bias).map(self.opt.state)
    def create_opt(self):
        self.opt = self.opt_func(self.splitter(self.model), lr=self.lr)
        if not self.wd_bn_bias:
            for p in self._bn_bias_state(True ): p['do_wd'] = False
        if self.train_bn:
            for p in self._bn_bias_state(False): p['force_train'] = True

    def _split(self, b):
        i = getattr(self.dbunch, 'n_inp', 1 if len(b)==1 else len(b)-1)
        self.xb,self.yb = b[:i],b[i:]

    def all_batches(self):
        self.n_iter = len(self.dl)
        for o in enumerate(self.dl): self.one_batch(*o)

    def one_batch(self, i, b):
        self.iter = i
        try:
            self._split(b);                                  self('begin_batch')
            self.pred = self.model(*self.xb);                self('after_pred')
            if len(self.yb) == 0: return
            self.loss = self.loss_func(self.pred, *self.yb); self('after_loss')
            if not self.training: return
            self.loss.backward();                            self('after_backward')
            self.opt.step();                                 self('after_step')
            self.opt.zero_grad()
        except CancelBatchException:                         self('after_cancel_batch')
        finally:                                             self('after_batch')

    def _do_begin_fit(self, n_epoch):
        self.n_epoch,self.loss = n_epoch,tensor(0.);         self('begin_fit')

    def _do_epoch_train(self):
        try:
            self.dl = self.dbunch.train_dl;                  self('begin_train')
            self.all_batches()
        except CancelTrainException:                         self('after_cancel_train')
        finally:                                             self('after_train')

    def _do_epoch_validate(self, ds_idx=1, dl=None):
        if dl is None: dl = self.dbunch.dls[ds_idx]
        try:
            self.dl = dl;                                    self('begin_validate')
            with torch.no_grad(): self.all_batches()
        except CancelValidException:                         self('after_cancel_validate')
        finally:                                             self('after_validate')

    def fit(self, n_epoch, lr=None, wd=defaults.wd, cbs=None, reset_opt=False):
        with self.added_cbs(cbs):
            if reset_opt or not self.opt: self.create_opt()
            self.opt.set_hypers(wd=wd, lr=self.lr if lr is None else lr)

            try:
                self._do_begin_fit(n_epoch)
                for epoch in range(n_epoch):
                    try:
                        self.epoch=epoch;          self('begin_epoch')
                        self._do_epoch_train()
                        self._do_epoch_validate()
                    except CancelEpochException:   self('after_cancel_epoch')
                    finally:                       self('after_epoch')

            except CancelFitException:             self('after_cancel_fit')
            finally:                               self('after_fit')

    def validate(self, ds_idx=1, dl=None, cbs=None):
        self.epoch,self.n_epoch,self.loss = 0,1,tensor(0.)
        if dl is None: dl = self.dbunch.dls[ds_idx]
        with self.added_cbs(cbs), self.no_logging():
            self(_before_epoch)
            self._do_epoch_validate(ds_idx, dl)
            self(_after_epoch)
        return self.recorder.values[-1]

    def get_preds(self, ds_idx=1, dl=None, with_input=False, with_loss=False, with_decoded=False, act=None):
        self.epoch,self.n_epoch,self.loss = 0,1,tensor(0.)
        cb = GatherPredsCallback(with_input=with_input, with_loss=with_loss)
        with self.no_logging(), self.added_cbs(cb), self.loss_not_reduced():
            self(_before_epoch)
            self._do_epoch_validate(ds_idx, dl)
            self(_after_epoch)
            if act is None: act = getattr(self.loss_func, 'activation', noop)
            preds = act(torch.cat(cb.preds))
            res = (preds, detuplify(tuple(torch.cat(o) for o in zip(*cb.targets))))
            if with_decoded: res = res + (getattr(self.loss_func, 'decodes', noop)(preds),)
            if with_input: res = (tuple(_try_concat(o) for o in zip(*cb.inputs)),) + res
            if with_loss:  res = res + (torch.cat(cb.losses),)
            return res

    def predict(self, item, rm_type_tfms=0):
        dl = test_dl(self.dbunch, [item], rm_type_tfms=rm_type_tfms)
        inp,preds,_ = self.get_preds(dl=dl, with_input=True)
        dec_preds = getattr(self.loss_func, 'decodes', noop)(preds)
        i = getattr(self.dbunch, 'n_inp', -1)
        full_dec = self.dbunch.decode_batch((*inp,dec_preds))[0][i:]
        return detuplify(full_dec),dec_preds[0],preds[0]

    def show_results(self, ds_idx=0, dl=None, max_n=10, **kwargs):
        if dl is None: dl = self.dbunch.dls[ds_idx]
        b = dl.one_batch()
        _,_,preds = self.get_preds(dl=[b], with_decoded=True)
        self.dbunch.show_results(b, preds, max_n=max_n, **kwargs)

    def show_training_loop(self):
        loop = ['Start Fit', 'begin_fit', 'Start Epoch Loop', 'begin_epoch', 'Start Train', 'begin_train',
                'Start Batch Loop', 'begin_batch', 'after_pred', 'after_loss', 'after_backward',
                'after_step', 'after_cancel_batch', 'after_batch','End Batch Loop','End Train',
                'after_cancel_train', 'after_train', 'Start Valid', 'begin_validate','Start Batch Loop',
                '**CBs same as train batch**', 'End Batch Loop', 'End Valid', 'after_cancel_validate',
                'after_validate', 'End Epoch Loop', 'after_cancel_epoch', 'after_epoch', 'End Fit',
                'after_cancel_fit', 'after_fit']
        indent = 0
        for s in loop:
            if s.startswith('Start'): print(f'{" "*indent}{s}'); indent += 2
            elif s.startswith('End'): indent -= 2; print(f'{" "*indent}{s}')
            else: print(f'{" "*indent} - {s:15}:', self.ordered_cbs(s))

    @contextmanager
    def no_logging(self): return replacing_yield(self, 'logger', noop)

    @contextmanager
    def loss_not_reduced(self):
        if hasattr(self.loss_func, 'reduction'): return replacing_yield(self.loss_func, 'reduction', 'none')
        else: return replacing_yield(self, 'loss_func', partial(self.loss_func, reduction='none'))

    def save(self, file, with_opt=True):
        if rank_distrib(): return # don't save if slave proc
        file = join_path_file(file, self.path/self.model_dir, ext='.pth')
        save_model(file, self.model, getattr(self,'opt',None), with_opt)

    def load(self, file, with_opt=None, device=None, strict=True):
        if device is None: device = self.dbunch.device
        if self.opt is None: self.create_opt()
        file = join_path_file(file, self.path/self.model_dir, ext='.pth')
        load_model(file, self.model, self.opt, with_opt=with_opt, device=device, strict=strict)
        return self

Learner.x,Learner.y = add_props(lambda i,x: detuplify((x.xb,x.yb)[i]))

#Cell
add_docs(Learner, "Group together a `model`, some `dbunch` and a `loss_func` to handle training",
    add_cbs="Add `cbs` to the list of `Callback` and register `self` as their learner",
    add_cb="Add `cb` to the list of `Callback` and register `self` as their learner",
    remove_cbs="Remove `cbs` from the list of `Callback` and deregister `self` as their learner",
    remove_cb="Add `cb` from the list of `Callback` and deregister `self` as their learner",
    added_cbs="Context manage that temporarily adds `cbs`",
    ordered_cbs="Return a list of `Callback` for one step `cb_func` in the training loop",
    create_opt="Create an optimizer with `lr`",
    one_batch="Train or evaluate `self.model` on batch `(xb,yb)`",
    all_batches="Train or evaluate `self.model` on all batches of `self.dl`",
    fit="Fit `self.model` for `n_epoch` using `cbs`. Optionally `reset_opt`.",
    validate="Validate on `dl` with potential new `cbs`.",
    get_preds="Get the predictions and targets on the `ds_idx`-th dbunchset or `dl`, optionally `with_input` and `with_loss`",
    predict="Return the prediction on `item`, fully decoded, loss function decoded and probabilities",
    show_results="Show some predictions on `ds_idx`-th dbunchset or `dl`",
    show_training_loop="Show each step in the training loop",
    no_logging="Context manager to temporarily remove `logger`",
    loss_not_reduced="A context manager to evaluate `loss_func` with reduction set to none.",
    save="Save model and optimizer state (if `with_opt`) to `self.path/self.model_dir/file`",
    load="Load model and optimizer state (if `with_opt`) from `self.path/self.model_dir/file` using `device`"
)

#Cell
class VerboseCallback(Callback):
    "Callback that prints the name of each event called"
    def __call__(self, event_name):
        print(event_name)
        super().__call__(event_name)

#Cell
@docs
class Metric():
    "Blueprint for defining a metric"
    def reset(self): pass
    def accumulate(self, learn): pass
    @property
    def value(self): raise NotImplementedError

    @property
    def name(self): return class2attr(self, 'Metric')

    _docs = dict(
        reset="Reset inner state to prepare for new computation",
        name="Name of the `Metric`, camel-cased and with Metric removed",
        accumulate="Use `learn` to update the state with new results",
        value="The value of the metric")

#Cell
def _maybe_reduce(val):
    if num_distrib()>1:
        val = val.clone()
        torch.distributed.all_reduce(val, op=torch.distributed.ReduceOp.SUM)
        val /= num_distrib()
    return val

#Cell
class AvgMetric(Metric):
    "Average the values of `func` taking into account potential different batch sizes"
    def __init__(self, func):  self.func = func
    def reset(self):           self.total,self.count = 0.,0
    def accumulate(self, learn):
        bs = find_bs(learn.yb)
        self.total += to_detach(_maybe_reduce(self.func(learn.pred, *learn.yb)))*bs
        self.count += bs
    @property
    def value(self): return self.total/self.count if self.count != 0 else None
    @property
    def name(self):  return self.func.__name__

#Cell
class AvgLoss(Metric):
    "Average the losses taking into account potential different batch sizes"
    def reset(self):           self.total,self.count = 0.,0
    def accumulate(self, learn):
        bs = find_bs(learn.yb)
        self.total += to_detach(_maybe_reduce(learn.loss.mean()))*bs
        self.count += bs
    @property
    def value(self): return self.total/self.count if self.count != 0 else None
    @property
    def name(self):  return "loss"

#Cell
class AvgSmoothLoss(Metric):
    "Smooth average of the losses (exponentially weighted with `beta`)"
    def __init__(self, beta=0.98): self.beta = beta
    def reset(self):               self.count,self.val = 0,tensor(0.)
    def accumulate(self, learn):
        self.count += 1
        self.val = torch.lerp(to_detach(learn.loss.mean()), self.val, self.beta)
    @property
    def value(self): return self.val/(1-self.beta**self.count)

#Cell
from fastprogress.fastprogress import format_time

def _maybe_item(t):
    t = t.value
    return t.item() if isinstance(t, Tensor) and t.numel()==1 else t

#Cell
class Recorder(Callback):
    "Callback that registers statistics (lr, loss and metrics) during training"
    run_after = TrainEvalCallback

    def __init__(self, add_time=True, train_metrics=False, beta=0.98):
        self.add_time,self.train_metrics = add_time,train_metrics
        self.loss,self.smooth_loss = AvgLoss(),AvgSmoothLoss(beta=beta)

    def begin_fit(self):
        "Prepare state for training"
        self.lrs,self.iters,self.losses,self.values = [],[],[],[]
        names = self._valid_mets.attrgot('name')
        if self.train_metrics: names = names.map('train_{}') + names.map('valid_{}')
        else:                  names = L('train_loss', 'valid_loss') + names[1:]
        if self.add_time: names.append('time')
        self.metric_names = 'epoch'+names
        self.smooth_loss.reset()

    def after_batch(self):
        "Update all metrics and records lr and smooth loss in training"
        if len(self.yb) == 0: return
        mets = self._train_mets if self.training else self._valid_mets
        for met in mets: met.accumulate(self.learn)
        if not self.training: return
        self.lrs.append(self.opt.hypers[-1]['lr'])
        self.losses.append(self.smooth_loss.value)
        self.learn.smooth_loss = self.smooth_loss.value

    def begin_epoch(self):
        "Set timer if `self.add_time=True`"
        self.cancel_train,self.cancel_valid = False,False
        if self.add_time: self.start_epoch = time.time()
        self.log = L(getattr(self, 'epoch', 0))

    def begin_train   (self): self._train_mets[1:].map(Self.reset())
    def begin_validate(self): self._valid_mets.map(Self.reset())
    def after_train   (self): self.log += self._train_mets.map(_maybe_item)
    def after_validate(self): self.log += self._valid_mets.map(_maybe_item)
    def after_cancel_train(self):    self.cancel_train = True
    def after_cancel_validate(self): self.cancel_valid = True

    def after_epoch(self):
        "Store and log the loss/metric values"
        self.values.append(self.log[1:].copy())
        if self.add_time: self.log.append(format_time(time.time() - self.start_epoch))
        self.logger(self.log)
        self.iters.append(self.smooth_loss.count)

    @property
    def _train_mets(self):
        if getattr(self, 'cancel_train', False): return L()
        return L(self.smooth_loss) + (self.metrics if self.train_metrics else L())

    @property
    def _valid_mets(self):
        if getattr(self, 'cancel_valid', False): return L()
        return L(self.loss) + self.metrics

    def plot_loss(self, skip_start=5, with_valid=True):
        plt.plot(self.losses[skip_start:], label='train')
        if with_valid:
            plt.plot(self.iters, L(self.values).itemgot(0), label='valid')
            plt.legend()

#Cell
add_docs(Recorder,
         begin_train = "Reset loss and metrics state",
         after_train = "Log loss and metric values on the training set (if `self.training_metrics=True`)",
         begin_validate = "Reset loss and metrics state",
         after_validate = "Log loss and metric values on the validation set",
         after_cancel_train = "Ignore training metrics for this epoch",
         after_cancel_validate = "Ignore validation metrics for this epoch",
         plot_loss = "Plot the losses from `skip_start` and onward")

defaults.callbacks = [TrainEvalCallback, Recorder]

#Cell
@patch
def freeze_to(self:Learner, n):
    if self.opt is None: self.create_opt()
    self.opt.freeze_to(n)

@patch
def freeze(self:Learner): self.freeze_to(-1)

@patch
def unfreeze(self:Learner): self.freeze_to(0)

add_docs(Learner,
         freeze_to="Freeze parameter groups up to `n`",
         freeze="Freeze up to last parameter group",
         unfreeze="Unfreeze the entire model")

#Cell
@patch
def export(self:Learner, fname='export.pkl'):
    "Export the content of `self` without the items and the optimizer state for inference"
    if rank_distrib(): return # don't export if slave proc
    old_dbunch = self.dbunch
    self.dbunch = dbunch.new_empty()
    state = self.opt.state_dict()
    self.opt = None
    with warnings.catch_warnings():
        #To avoid the warning that come from PyTorch about model not being checked
        warnings.simplefilter("ignore")
        torch.save(self, open(self.path/fname, 'wb'))
    self.create_opt()
    self.opt.load_state_dict(state)
    self.dbunch = old_dbunch
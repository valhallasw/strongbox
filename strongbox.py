"""
strongbox: smart data classes
"""
from types import StringType, LambdaType, ListType, NoneType
import narrative as narr
import re
import unittest
import warnings

_eggData = {
   'version': '0.9.1a',
   'description': 'smart data objects with run-time type checking',
}


Unspecified = object() # just a type distinct from None

class attr(property):
    """
    A property that checks types
    """
    
    def __init__(self, typ, default=Unspecified, okay=None, allowNone=True):
        self.name = None
        self.type = typ
        self.determineDefault(typ, default)
        self.setOkay(okay)
        self.allowNone = allowNone

        property.__init__(self,
            fget = self.wrapGetter,
            fset = self.wrapSetter,
            fdel = None,
            doc = None)

    def determineDefault(self, typ, default):
        """
        assigns the default value or generates one
        based on the type if a default was not provided
        """
        if default is Unspecified:
            if typ in (str, unicode, int, float, long, bool):
                self.default = typ()
            else:
                self.default = None
        else:
            self.default = default

    
    def setOkay(self, okay):
        """
        Creates the data validation method isOkay
        """
        self.okay = okay # keep for (eg) list dropdown forms
        def select(case=type(okay)):
            if StringType == case:
                return lambda v : re.compile(okay).match(v)
            elif LambdaType == case:
                return okay
            elif ListType == case:
                return okay.__contains__
            elif NoneType == case:
                return lambda v: True
            else:
                raise TypeError(".okay cannot be %s" % case)
        self.isOkay = select()



    def initialValue(self, instance=None): 
        """
        BlackBox.__init__ uses return value for instance.private.xxx
        """
        self.forceLambda()
        return self.attemptCast(self.default)


    def attemptCast(self, value):
        """
        If possible, returns the value cast as the attribute type.
        """
        if value is None:
            return None # str(None) returns 'None', so we need a special case.
        elif isinstance(value, self.type):
            return value
        try:
            return self.type(value)
        except Exception, e:
            if value=="":
                # @TODO: remove this convenience for http browsers
                # i'm afraid a lot of untested code is depending
                # on it at the moment though. :/
                return self.handleNone()
            raise TypeError(self.__name__,value,self.type,str(e))


    def handleNone(self):
        """
        Determines how to handle None values based on .allowNone
        """
        if not self.allowNone:
            raise ValueError("%s cannot be None" % self.name)
        return None


    def forceLambda(self):
        """
        Takes the attribute type out of a lambda.
        This is what enables forward or circular references.
        """
        if type(self.type) == LambdaType:
            self.type = self.type() # get rid of lambda: wrapper


    def sanitize(self, value):
        """
        top level method: cleanvalue = attr.sanitize(value)
        may throw TypeError or ValueError
        """
        return self.scrubValue(self.scrubType(value))

    def scrubType(self, value):
        if (isinstance(value, self.type)) or (value is None):
            return value
        else:
            return self.attemptCast(value)

    def scrubValue(self, value):
        """
        Returns the value if it's okay, else raises ValueError
        """
        if value is None:
            return self.handleNone()
        elif not self.isOkay(value):
            raise ValueError(self.__name__, repr(value))
        return value # so the instance can store it

    ## getters and setters ##

    def wrapSetter(self, instance, value):
        self.setter(instance, value)

    def setter(self, instance, value):
        val = self.sanitize(value)
        setattr(instance.private, self.name, val)
        instance.onSet(self.name, val)

    def wrapGetter(self, instance):
        return self.getter(instance)
    
    def getter(self, instance):
        instance.onGet(self.name)
        return getattr(instance.private, self.name)



class link(attr):
    """
    Represents a link from one BlackBox/StrongBox to another    
    """
    def __init__(self, klass):
        self.type = klass
        self.default = None
        self.allowNone = True
        
    def sanitize(self, value):
        return self.scrubType(value)



class TypedList(list):
    
    def __init__(self, klass, owner, backlink):
        super(TypedList, self)
        self.setType(klass)
        self.backlink = backlink
        self.owner = owner

    def setType(self, type):
        self.type = type

    def append(self, other):
        if type(other) == self.type:
            super(TypedList, self).append(other)
        else:
            raise TypeError, "Can't append %s to TypedList(%s)" \
                  % (type(other), self.type)
        if self.backlink is not None:
            setattr(other, self.backlink, self.owner)
    
    def __lshift__(self, other):
        self.append(other)
        return other

    

class linkset(attr):
    """
    Represents a link to several Boxes of the same type.
    """
    def __init__(self, type, back):
        """
        type: the type of objects in the collection
        back: the name of the backlink in the child (can be None)

        For example, parent.children might have a backlink of
        child.parent so you'd say:

        class Parent(StrongBox):
            children = linkset(Child, 'parent')

        """
        self.type = type
        self.back = back

    def initialValue(self, instance):
        self.forceLambda()
        return TypedList(self.type, instance, self.back)

    def sanitize(self, other):
        raise AttributeError("can't assign to linksets (only append/delete)")
    


class Private(object):
    """
    A plain old object. Holds private data for its owner.
    """
    

class Strict(object):
    """
    Strict objects contain a .private sub-object
    """
    def __init__(self, **kwargs):
        self.private = Private()
        


class Observable(Strict):
    """
    A mix-in that allows notifying observers when something changes.
    """
    def __init__(self, **kw):
        super(Observable, self).__init__(**kw)
        self.private.observers = []

    def addObserver(self, callback):
        self.private.observers.append(callback)

    def removeObserver(self, callback):
        if callback in self.private.observers:
            self.private.observers.remove(callback)
        
    def notifyObservers(self, slot, value):
        for callback in self.private.observers:
            callback(self, slot, value)

    def onSet(self, slot, value):
        self.notifyObservers(slot, value)
        self.private.isDirty = True
        


class Injectable(Strict):
    """
    A mix-in that allows lazy loading.
    """
    def __init__(self, **kw):
        super(Injectable, self).__init__(**kw)
        self.private.isDirty = True # so new objects get saved
        self.private.injectors = []

    def addInjector(self, callback):
        self.private.injectors.append(callback)

    def removeInjector(self, callback):
        if callback in self.private.injectors:
            self.private.injectors.remove(callback)

    def notifyInjectors(self, slot):
        for callback in self.private.injectors:
            callback(self, slot)

    def onGet(self, slot):
        self.notifyInjectors(slot)
    

class MetaBox(type):
    """
    A meta-class that enables attribute

    This is a metaclass. It's used to build a
    new strongbox subclass, which can then be
    instantiated.

    It's just a normal object that builds a class.       
    For an overview of metaclasses, see:

        http://www.python.org/2.2.3/descrintro.html#metaclasses

    You should not use this class directly.
    Rather, subclass StrongBox.
    """
    def __init__(klass, name, bases, dict):
        klass.dict = dict
        klass.attrs = [k for k in dict if isinstance(dict[k], attr)]
        klass.tellAttributesTheirNames()
        klass.addAccessors()
        klass.addCalculatedFields()
        
    def tellAttributesTheirNames(klass):
        # this is so attrs can report their
        # names during errors.
        for slot in klass.attrs:
            klass.dict[slot].name = slot
            klass.dict[slot].__name__ = slot

    def addAccessors(klass):
        """
        This handles get_xxx and set_xxx methods for
        all members that are already defined as attributes.
        If these methods are not defined, they are
        created on the fly.
        """
        for slot in klass.attrs:

            getter = klass.dict.get("get_%s" % slot)
            setter = klass.dict.get("set_%s" % slot)

            # __init__ is the only way to change .fset and .fget:
            prop = klass.dict[slot]
            if getter or setter or prop.__class__ in [link,linkset]:
                property.__init__(prop,
                                  getter or prop.wrapGetter,
                                  setter or prop.wrapSetter)

    def addCalculatedFields(klass):
        """
        This handles get_xxx and set_xxx methods for
        members that have *not* been previously defined
        as attributes, allowing you to create virtual
        or calculated members.
        """
        getter = {}
        setter = {}
        
        for name in klass.dict:            
            if name.startswith("get_") or name.startswith("set_"):
                slot = name[4:]
                if slot not in klass.attrs:
                    if name.startswith("get_"):
                        getter[slot] = klass.dict[name]
                    elif name.startswith("set_"):
                        setter[slot] = klass.dict[name]

        from sets import Set
        for key in Set(getter.keys() + setter.keys()):
            setattr(klass, key, property(getter.get(key), setter.get(key)))
                    


class BlackBox(Strict):
    """
    A class whose slots are all typed properties
    """
    __metaclass__=MetaBox

    def __init__(self, **kwargs):
        super(BlackBox, self).__init__()
        for name, attr in self.getSlots():
            if type(attr) == property: continue
            setattr(self.private, name, attr.initialValue(self))

    def __setattr__(self, slot, value):
        def fail(reason):
            raise AttributeError("can't set attribute %s on %s instance: %s" %
                                 (slot, self.__class__.__name__, reason))
        # for some reason, hasattr(self, slot) causes problems for injectors
        # i'm not sure why. in any case, this will do for now.
        if slot == "private" or hasattr(self.__class__, slot):
            try:
                super(BlackBox, self).__setattr__(slot, value)
            except AttributeError, e:
                fail(str(e))
        else:
            fail('not a member of this class')

    def update(self, **kwargs):
        """
        Like dict.update
        """
        for k in kwargs:
            setattr(self, k, kwargs[k])


    def noisyUpdate(self, **kwargs):
        """
        Like update but allows junk (eg, from an HTTP POST)
        """
        for k in kwargs:
            if k in self.__class__.dict:
                setattr(self, k, kwargs[k])

    ## accessor hooks ##

    def onSet(self, slot, value):
        """
        onSet hook. Does nothing in BlackBox.
        """
        pass
    
    def onGet(self, slot):
        """
        onGet hook. Does nothing in BlackBox.
        """
        pass

    
    ## introspection ###

    def __repr__(self):
        # in links/linksets and in other cases where objects refer
        # back to each other, this could create an infinite loop,
        # so we only show plain attributes.
        return "%s(%s)" % (self.__class__.__name__ ,
                           ", ".join(["%s=%s" % (a, repr(getattr(self, a)))
                                      for a,v in self.attributeValues().items()]))


    def getSlots(self):
        """
        Returns a list of all name, attribute pairs.
        """
        myClass = self.__class__
        return sorted([(slot, theAttr)                   
                       for klass in (myClass,) + myClass.__bases__
                       for slot, theAttr in klass.__dict__.items()
                       if isinstance(theAttr, property)])


    def getSlotsOfType(self, t):
        """
        Returns a list of all name, attribute pairs of type t
        where t can be attr, link, linkset...
        """
        return [(slot, attr) for (slot, attr) in self.getSlots()
                if isinstance(attr, t)]

    def listWritableSlots(self):
        return [slot for (slot, attr) in self.getSlots()
                if attr.fset is not None]

    def attributeValues(self):
        """
        Return a dictionary
        """
        res = {}
        for name, prop in self.getSlots():
            if prop.__class__ == attr:
                res[name] = getattr(self, name)
        return res

         

class StrongBox(Injectable, Observable, BlackBox):
    """
    An observable, lazy-loadable base class for type checking data objects
    """
    def __init__(self, **kwargs):
        super(StrongBox, self).__init__()
        self.update(**kwargs)



"""
<p>For old times sake:</p>
"""

class Strongbox(StrongBox):
    def __init__(self, **kw):
        #warnings.warn("Strongbox is deprecated: use the upper case B :)")
        StrongBox.__init__(self, **kw)



"""
@TODO: Rename this as BoxDict?

note: this was moved here from zdc. It's useful for
zebra templates, but it's not really integrated
with strongbox yet.
"""
class BoxView:
    """
    Builds a view (dict/list data structure) from a Box
    """
    __ver__="$Id: BoxView.py,v 1.4 2006/01/20 18:22:45 sabren Exp $"

    def __init__(self,object):
        self.object = object

    def __getitem__(self, name):
        # this used to have a try..except block, but it made it
        # very hard to debug!
        try:
            res = getattr(self.object, name)
        except AttributeError, e:
            raise AttributeError("couldn't read attribute '%s' [%s]" % (name, e))

        if isinstance(res, tuple) or isinstance(res, linkset) or isinstance(res, list):
            return [BoxView(item) for item in res]
        else:
            return res

    def __getattr__(self, name):
        if name=="object":
            return getattr(super(BoxView, self), name)
        else:
            return getattr(self.object, name)

    def get(self, name, default=None):
        return getattr(self.object, name, default)

    def keys(self):
        return [k for k, v in self.object.getSlots()]



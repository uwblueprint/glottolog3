from datetime import date
import re
import json
import transaction
from collections import OrderedDict
from itertools import groupby

from marshmallow import ValidationError
from pyramid.httpexceptions import (
    HTTPNotAcceptable, HTTPNotFound, HTTPFound, HTTPMovedPermanently,
)
from pyramid.view import view_config
from sqlalchemy import and_, true, false, null, or_, exc
from sqlalchemy.sql.expression import func
from sqlalchemy.orm import joinedload
from clld.db.meta import DBSession
from clld.db.models.common import (
    Language, Source, LanguageIdentifier, Identifier, IdentifierType,
)
from clld.db.util import icontains
from clld.web.util.helpers import JS
from clld.web.util.htmllib import HTML
from clld.web.util.multiselect import MultiSelect
from clld.lib import bibtex
from clld.interfaces import IRepresentation
from clldutils.misc import slug

from glottolog3.models import (
    Languoid, LanguoidSchema, LanguoidStatus, LanguoidLevel, Macroarea, Doctype,
    IdentifierSchema, Refprovider, TreeClosureTable, BOOKKEEPING,
)
from glottolog3.config import CFG
from glottolog3.util import getRefs, get_params
from glottolog3.datatables import Refs
from glottolog3.models import Country, SPECIAL_FAMILIES, GLOTTOCODE_PATTERN
from glottolog3.adapters import get_selected_languages_map


YEAR_PATTERN = re.compile('[0-9]{4}$')

class LanguoidsMultiSelect(MultiSelect):
    def format_result(self, l):
        return dict(id=l.id, text=l.name, level=l.level.value)

    def get_options(self):
        opts = super(LanguoidsMultiSelect, self).get_options()
        opts['formatResult'] = JS('GLOTTOLOG3.formatLanguoid')
        opts['formatSelection'] = JS('GLOTTOLOG3.formatLanguoid')
        return opts


def iso(request):
    q = DBSession.query(Languoid).join(LanguageIdentifier).join(Identifier)\
        .filter(Identifier.type == IdentifierType.iso.value)\
        .filter(Identifier.name == request.matchdict['id']).first()
    if not q:
        return HTTPNotFound()
    params = {}
    if 'ext' in request.matchdict:
        params['ext'] = request.matchdict['ext']
    return HTTPFound(location=request.resource_url(q, **params))


def glottologmeta(request):
    q = DBSession.query(Languoid)
    qt = q.filter(Languoid.father_pk == null())
    res = {
        'last_update': DBSession.query(Language.updated)
        .order_by(Language.updated.desc()).first()[0],
        'number_of_families': qt.filter(Languoid.level == LanguoidLevel.family).count(),
        'number_of_isolates': qt.filter(Languoid.level == LanguoidLevel.language).count(),
    }
    bookkeeping = DBSession.query(Language).filter(Language.name == BOOKKEEPING).one()
    ql = q.filter(and_(
        Languoid.level == LanguoidLevel.language,
        Languoid.family_pk != bookkeeping.pk))
    res['number_of_languages'] = {'all': ql.count()}

    res['special_families'] = OrderedDict()
    res['number_of_languages']['l1'] = res['number_of_languages']['all']
    for name in SPECIAL_FAMILIES:
        l = qt.filter(Language.name == name).one()
        res['special_families'][name] = l
        res['number_of_languages'][name] = l.child_language_count
        res['number_of_languages']['l1'] -= l.child_language_count

    return res


def childnodes(request):
    if request.params.get('t') == 'select2':
        query = DBSession.query(Languoid.id, Languoid.name, Languoid.level)\
            .filter(icontains(Languoid.name, request.params.get('q')))
        total = query.count()
        ms = LanguoidsMultiSelect(request, None, None, url='x')
        return dict(
            results=[ms.format_result(l) for l in query.limit(100)],
            context={},
            more=total > 500)

    query = DBSession.query(
        Languoid.pk,
        Languoid.id,
        Languoid.name,
        Languoid.level,
        func.count(TreeClosureTable.child_pk).label('children'))\
        .filter(Language.pk == TreeClosureTable.parent_pk)\
        .filter(Language.active == true())

    if request.params.get('node'):
        query = query.filter(Languoid.father_pk == int(request.params['node']))
    else:
        # narrow down selection of top-level nodes in the tree:
        query = query.filter(Languoid.father_pk == null())
        if request.params.get('q'):
            query = query.filter(Language.name.contains(request.params.get('q')))

    query = query.group_by(
        Languoid.pk,
        Languoid.id,
        Languoid.name,
        Languoid.level).order_by(Language.name)
    return [{
        'label': ('%s (%s)' % (l.name, l.children - 1))
            if l.children > 1 else l.name,
        'glottocode': l.id,
        'lname': l.name,
        'id': l.pk,
        'level': l.level.value,
        #'children': l.children
        'load_on_demand': l.children > 1} for l in query]


def credits(request):
    return HTTPMovedPermanently(location=request.route_url('about'))


def glossary(request):
    return {
        'macroareas': DBSession.query(Macroarea).order_by(Macroarea.id),
        'doctypes': DBSession.query(Doctype).order_by(Doctype.name)}


def cite(request):
    return {'date': date.today(), 'refs': CFG['PUBLICATIONS']}


def downloads(request):
    return {}


def news(request):
    return {}


def contact(request):
    return {}


def about(request):
    return {}


def families(request):
    return {'dt': request.get_datatable('languages', Language, type='families')}


def getLanguoids(name=False,
                 iso=False,
                 namequerytype='part',
                 country=False,
                 multilingual=False,
                 inactive=False):
    """return an array of languoids responding to the specified criterion.
    """
    if not (name or iso or country):
        return []

    query = DBSession.query(Languoid)\
        .options(joinedload(Languoid.family))\
        .order_by(Languoid.name)

    if not inactive:
        query = query.filter(Language.active == True)

    if name:
        crit = [Identifier.type == 'name']
        ul_iname = func.unaccent(func.lower(Identifier.name))
        ul_name = func.unaccent(name.lower())
        if namequerytype == 'whole':
            crit.append(ul_iname == ul_name)
        else:
            crit.append(ul_iname.contains(ul_name))
        if not multilingual:
            crit.append(func.coalesce(Identifier.lang, '').in_((u'', u'eng', u'en')))
        crit = Language.identifiers.any(and_(*crit))
        query = query.filter(or_(icontains(Languoid.name, name), crit))
    elif country:
        return []  # pragma: no cover
    else:
        query = query.join(LanguageIdentifier, Identifier)\
            .filter(Identifier.type == IdentifierType.iso.value)\
            .filter(Identifier.name.contains(iso.lower()))
    return query


def quicksearch(request):
    message = None
    query = DBSession.query(Languoid)
    term = request.params['search'].strip()
    titlecase = term.istitle()
    term = term.lower()
    params = {'iso': '', 'country': '',
        'name': '', 'namequerytype': 'part', 'multilingual': ''}

    if not term:
        query = None
    elif len(term) < 3:
        query = None
        message = ('Please enter at least four characters for a name search '
            'or three characters for an iso code')
    elif len(term) == 3 and not titlecase:
        query = query.filter(Languoid.identifiers.any(
            type=IdentifierType.iso.value, name=term))
        kind = 'ISO 639-3'
    elif len(term) == 8 and GLOTTOCODE_PATTERN.match(term):
        query = query.filter(Languoid.id == term)
        kind = 'Glottocode'
    else:
        _query = query.filter(func.lower(Languoid.name) == term)
        if DBSession.query(_query.exists()).scalar():
            query = _query
        else:
            query = query.filter(or_(
                func.lower(Languoid.name).contains(term),
                Languoid.identifiers.any(and_(
                    Identifier.type == u'name',
                    Identifier.description == Languoid.GLOTTOLOG_NAME,
                    func.lower(Identifier.name).contains(term)))))

        kind = 'name part'
        params['name'] = term

    if query is None:
        languoids = []
    else:
        languoids = query.order_by(Languoid.name)\
            .options(joinedload(Languoid.family)).all()
        if not languoids:
            term_pre = HTML.kbd(term, style='white-space: pre')
            message = 'No matching languoids found for %s "' % kind + term_pre + '"'
        elif len(languoids) == 1:
            raise HTTPFound(request.resource_url(languoids[0]))

    map_, icon_map, family_map = get_selected_languages_map(request, languoids)
    layer = list(map_.get_layers())[0]
    if not layer.data['features']:
        map_ = None

    countries = json.dumps(['%s (%s)' % (c.name, c.id) for c in
        DBSession.query(Country).order_by(Country.description)])

    return {'message': message, 'params': params, 'languoids': languoids,
        'map': map_, 'countries': countries}


# ENDPOINTS ADDED BY BLUEPRINT
def bpsearch(request):
    message = None
    query = DBSession.query(Languoid)
    term = request.params['bpsearch'].strip().lower()
    params = {
            'name': term,
            'namequerytype': request.params['namequerytype'],
            'multilingual': 'multilingual' in request.params
            }

    if not term:
        query = None
    elif len(term) < 3:
        query = None
        message = ('Please enter at least three characters for a search.')
    elif len(term) == 8 and GLOTTOCODE_PATTERN.match(term):
        query = query.filter(Languoid.id == term)
        kind = 'Glottocode'
    else:
        # list of criteria to search languoids by
        crit = [Identifier.type == 'name']
        ul_iname = func.unaccent(func.lower(Identifier.name))
        ul_name = func.unaccent(term)
        if params['namequerytype'] == 'whole':
            crit.append(ul_iname == ul_name)
        else:
            crit.append(ul_iname.contains(ul_name))
        if not params['multilingual']:
            # restrict to English identifiers
            crit.append(func.coalesce(Identifier.lang, '').in_((u'', u'eng', u'en')))
        crit = Language.identifiers.any(and_(*crit))
        # add ISOs to query if length == 3
        iso = Languoid.identifiers.any(type=IdentifierType.iso.value, name=term) if len(term) == 3 else None
        query = query.filter(or_(
            icontains(Languoid.name, term),
            crit,
            iso))
        kind = 'name part'

    if query is None:
        languoids = []
    else:
        query.filter(Language.active == True)
        languoids = query.order_by(Languoid.name)\
            .options(joinedload(Languoid.family)).all()
        if not languoids:
            term_pre = HTML.kbd(term, style='white-space: pre')
            message = 'No matching languoids found for %s "' % kind + term_pre + '"'

    map_ = None

    countries = json.dumps(['%s (%s)' % (c.name, c.id) for c in
        DBSession.query(Country).order_by(Country.description)])

    return {'message': message, 'params': params, 'languoids': languoids,
            'map': map_, 'countries': countries}

def identifier_score(identifier, term):
    # sorting key method that will return a lower rank for greater similarity
    lower_id = identifier.lower()
    coverage = float(len(term))/len(lower_id)
    if lower_id == term:
        return 0
    elif lower_id.startswith(term):
        return 1 - coverage
    elif ' ' + term in lower_id:
        return 2 - coverage
    return 3 - coverage

def best_identifier_score(identifiers, term):
    rank = 3
    for i in identifiers:
        rank = min(rank,identifier_score(i.Identifier.name,term))
    return rank

@view_config(
        route_name='glottolog.search',
        request_method='GET',
        renderer='json')
def bp_api_search(request):
    query = DBSession.query(Languoid, LanguageIdentifier, Identifier).join(LanguageIdentifier).join(Identifier)
    term = request.params['q'].strip().lower()
    namequerytype = request.params.get('namequerytype', 'part').strip().lower()
    multilingual = request.params.get('multilingual', None)

    if not term:
        query = None
    elif len(term) < 3:
        return [{'message': 'Please enter at least three characters for a search.'}]
    elif len(term) == 8 and GLOTTOCODE_PATTERN.match(term):
        query = query.filter(Languoid.id == term)
        kind = 'Glottocode'
    else:
        # list of criteria to search languoids by
        filters = []
        ul_iname = func.unaccent(func.lower(Identifier.name))
        ul_name = func.unaccent(term)
        if namequerytype == 'whole':
            filters.append(ul_iname == ul_name)
        else:
            filters.append(ul_iname.contains(ul_name))
        if not multilingual:
            # restrict to English identifiers
            filters.append(func.coalesce(Identifier.lang, '').in_((u'', u'eng', u'en')))

        query = query.filter(and_(*filters))
        kind = 'name part'

    if query is None:
        return []
    else:
        results = query.order_by(Languoid.name)\
                .options(joinedload(Languoid.family)).all()
        if not results:
            return []

    # group together identifiers that matched for the same languoid
    mapped_results = {k:list(g) for k, g in groupby(results, lambda x: x.Languoid)}
    # order languoid results by greatest identifier similarity, and then by name to break ties + consistency
    ordered_results = OrderedDict(sorted(mapped_results.items(), key=lambda k, v: (best_identifier_score(v,term), k.name)))

    return [{
        'name': k.name,
        'glottocode': k.id,
        'iso': k.hid if k.hid else '',
        'level': k.level.name,
        'matched_identifiers': sorted(set([i.Identifier.name for i in v]), key=lambda x: identifier_score(x, term))  if kind != 'Glottocode' else [],
        } for k, v in ordered_results.items()]


@view_config(
        route_name='glottolog.add_identifier',
        renderer='json')
def add_identifier(request):
    gcode = request.matchdict['glottocode'].lower()

    languoid = DBSession.query(Language) \
                        .filter_by(id='{0}'.format(gcode)) \
                        .first()

    if languoid == None:
        request.response.status = 404 
        return {'error': 'No language found with glottocode: {}'.format(gcode)}
    
    try:
        identifier, errors = IdentifierSchema().load(request.json_body)
    except (ValueError, ValidationError) as e:
        request.response.status = 400
        return {'error': '{}'.format(e)}
    if errors:
        request.response.status = 400
        return {'error': errors}
    
    try:
        DBSession.add(identifier)
        DBSession.add(
            LanguageIdentifier(language=languoid, identifier=identifier))
        DBSession.flush()
        result = json.dumps(IdentifierSchema().dump(identifier))
    except exc.SQLAlchemyError as e:
        request.response.status = 400
        DBSession.rollback()
        return { 'error': '{}'.format(e) }
    
    # So we can use identifier object without session
    transaction.commit()

    return result 


def query_identifier(type, name):
    type = type.lower()
    name = name.title() if type == 'name' else name.lower()

    id_query = DBSession.query(Identifier) \
                        .filter(and_(Identifier.name == name,
                                     Identifier.type == type))
    result = [id_query, None]

    if id_query.count() == 0:
        result[1] = ('No identifier found with '
                     'type: {0}, and name: {1}').format(type, name)
    return result


@view_config(
        route_name='glottolog.get_identifier',
        renderer='json')
def get_identifier(request):
    id_query, errors = query_identifier(request.matchdict['type'],
                                        request.matchdict['name'])
    if errors:
        request.response.status = 404
        return {'error': errors}

    identifier = id_query.first()

    return json.dumps(IdentifierSchema().dump(identifier)) 


@view_config(
        route_name='glottolog.put_identifier',
        renderer='json')
def put_identifier(request):
    REQ_FIELDS = ['name', 'type'] 
    OPT_FIELDS = ['description', 'lang']
    is_partial = False
    new_identifier = request.json_body
    id_query, errors = query_identifier(request.matchdict['type'],
                                        request.matchdict['name'])
    if errors:
        request.response.status = 404
        return {'error': errors}

    identifier = id_query.first()

    if not any (k in new_identifier for k in REQ_FIELDS):
        is_partial = True 
    else:
        all_fields = REQ_FIELDS + OPT_FIELDS
        update_fields = (k for k in all_fields if k not in new_identifier)
        for field in update_fields:
            new_identifier[field] = getattr(identifier, field)

    try:
        data, errors = IdentifierSchema(partial=is_partial).load(new_identifier)
    except (ValueError, ValidationError) as e:
        request.response.status = 400
        return {'error': '{}'.format(e)}
    if errors:
        request.response.status = 400
        return {'error': errors}

    try:
        for key in new_identifier:
            # Cannot direct lookup on identifier object
            setattr(identifier, key, getattr(data, key))

        DBSession.flush()
        result = json.dumps(IdentifierSchema().dump(identifier))
    except exc.SQLAlchemyError as e:
        request.response.status = 400
        DBSession.rollback()
        return { 'error': '{}'.format(e) }
    
    # Commit if no errors
    transaction.commit()

    return result 


@view_config(
        route_name='glottolog.delete_identifier',
        renderer='json')
def delete_identifier(request):
    id_query, errors = query_identifier(request.matchdict['type'],
                                        request.matchdict['name'])
    if errors:
        request.response.status = 404
        return {'error': errors}

    try:
        DBSession.query(LanguageIdentifier) \
                 .filter(LanguageIdentifier.identifier == id_query.first()) \
                 .delete()
        id_query.delete()
        DBSession.flush()
    except exc.SQLAlchemyError as e:
        request.response.status = 400
        DBSession.rollback()
        return { 'error': '{}'.format(e) }
    
    # Commit if no errors
    transaction.commit()

    # Return empty body for success
    return {} 


def query_languoid(DBSession, id):
    return DBSession.query(Languoid) \
                    .filter(Languoid.id == id) \
                    .filter(Language.active == True) \
                    .first()


@view_config(
    route_name='glottolog.get_languoid',
    renderer='json')
def get_languoid(request):
    glottocode = request.matchdict['glottocode']
    languoid = query_languoid(DBSession, glottocode)
    if languoid is None:
        request.response.status = 404
        return {'error': 'Not a valid languoid ID'}
    return LanguoidSchema().dump(languoid).data


@view_config(
    route_name='glottolog.add_languoid',
    request_method='POST',
    renderer='json')
def add_languoid(request):
    json_data = request.json_body

    try:
        data, errors = LanguoidSchema().load(json_data)
    except ValueError:
        request.response.status = 400
        return {'error': 'Not a valid languoid level'}
    if errors:
        request.response.status = 400
        return {'error': errors}

    try:
        DBSession.add(Languoid(**data))
        DBSession.flush()
    except exc.SQLAlchemyError as e:
        request.response.status = 400
        DBSession.rollback()
        return {'error': "{}".format(e)}

    request.response.status = 201
    return LanguoidSchema().dump(Languoid(**data)).data


@view_config(
    route_name='glottolog.put_languoid',
    request_method='PUT',
    renderer='json')
def put_languoid(request):
    glottocode = request.matchdict['glottocode']
    languoid = query_languoid(DBSession, glottocode)
    if languoid is None:
        request.response.status = 404
        return {'error': 'Not a valid languoid ID'}

    json_data = request.json_body
    try:
        data, errors = LanguoidSchema(partial=True).load(json_data)
    except ValueError:
        request.response.status = 400
        return {'error': 'Not a valid languoid level'}
    if errors:
        request.response.status = 400
        return {'error': errors}

    try:
        for key, value in data.items():
            setattr(languoid, key, value)
        DBSession.flush()
    except exc.SQLAlchemyError as e:
        request.response.status = 400
        DBSession.rollback()
        return {'error': "{}".format(e)}

    return LanguoidSchema().dump(languoid).data


@view_config(
    route_name='glottolog.delete_languoid',
    request_method='DELETE',
    renderer='json')
def delete_languoid(request):
    glottocode = request.matchdict['glottocode']
    languoid = query_languoid(DBSession, glottocode)
    if languoid is None:
        request.response.status = 404
        return {'error': 'Not a valid languoid ID'}

    try:
        languoid.active = False
        DBSession.flush()
    except exc.SQLAlchemyError as e:
        request.response.status = 400
        DBSession.rollback()
        return {'error': "{}".format(e)}

    request.response.status = 204
    return LanguoidSchema().dump(languoid).data

@view_config(
    route_name='glottolog.add_descendant',
    request_method='POST',
    renderer='json')
def add_descendant(request):
    glottocode = request.matchdict['glottocode']
    languoid = query_languoid(DBSession, glottocode)
    if languoid is None:
        request.response.status = 404
        return {'error': 'Not a valid languoid ID'}

    d_glottocode = request.json_body.get('descendant')
    descendant = query_languoid(DBSession, d_glottocode)
    if not descendant:
        request.response.status = 404
        return {'error': 'descendant specified in payload does not exist'}

    try:
        descendants = languoid.descendants
        descendants.append(descendant)
        setattr(languoid, 'descendants', descendants)
        DBSession.flush()
    except exc.SQLAlchemyError as e:
        DBSession.rollback()
        return { 'error': '{}'.format(e) }

    return LanguoidSchema().dump(languoid).data


@view_config(
    route_name='glottolog.add_child',
    request_method='POST',
    renderer='json')
def add_child(request):
    glottocode = request.matchdict['glottocode']
    languoid = query_languoid(DBSession, glottocode)
    if languoid is None:
        request.response.status = 404
        return {'error': 'Not a valid languoid ID'}

    c_glottocode = request.json_body.get('child')
    child = query_languoid(DBSession, c_glottocode)
    if not child:
        request.response.status = 404
        return {'error': 'child specified in payload does not exist'}

    try:
        children = languoid.children
        children.append(child)
        setattr(languoid, 'children', children)
        DBSession.flush()
    except exc.SQLAlchemyError as e:
        DBSession.rollback()
        return { 'error': '{}'.format(e) }

    return LanguoidSchema().dump(languoid).data
# BLUEPRINT CODE END


def languages(request):
    if request.params.get('search'):
        return quicksearch(request)

    elif request.params.get('bpsearch'):
        return bpsearch(request)

    res = dict(
        countries=json.dumps([
            '%s (%s)' % (c.name, c.id) for c in
            DBSession.query(Country).order_by(Country.description)]),
        params={
            'name': '',
            'iso': '',
            'namequerytype': 'part',
            'country': ''},
        message=None)

    for param, default in res['params'].items():
        res['params'][param] = request.params.get(param, default).strip()

    if res['params']['country']:
        country = res['params']['country']
        try:
            alpha2 = country.split('(')[1].split(')')[0] \
                if len(country) > 2 else country.upper()
            raise HTTPFound(location=request.route_url(
                'languages_alt', ext='map.html', _query=dict(country=alpha2)))
        except IndexError:
            pass

    res['params']['multilingual'] = 'multilingual' in request.params

    if request.params.get('alnum'):
        l = Languoid.get(request.params.get('alnum'), default=None)
        if l:
            raise HTTPFound(location=request.resource_url(l))
        res['message'] = 'No matching languoids found'

    if (res['params']['iso'] and len(res['params']['iso']) < 2) or (
            res['params']['name']
            and len(res['params']['name']) < 2
            and res['params']['namequerytype'] == 'part'):
        res.update(
            message='Please enter at least two characters to search',
            map=None,
            languoids=[])
        return res

    languoids = list(getLanguoids(**res['params']))
    if not languoids and \
            (res['params']['name'] or res['params']['iso'] or res['params']['country']):
        res['message'] = 'No matching languoids found'
    #if len(languoids) == 1:
    #    raise HTTPFound(request.resource_url(languoids[0]))

    map_, icon_map, family_map = get_selected_languages_map(request, languoids)

    layer = list(map_.get_layers())[0]
    if not layer.data['features']:
        map_ = None
    res.update(map=map_, languoids=languoids)
    return res

def langdoccomplexquery(request):
    res = {
        'dt': None,
        'doctypes': DBSession.query(Doctype).order_by(Doctype.id),
        'macroareas': DBSession.query(Macroarea).order_by(Macroarea.id),
        'ms': {}
    }

    for name, cls, kw in [
        ('languoids', LanguoidsMultiSelect, dict(
            url=request.route_url('glottolog.childnodes'))),
        ('macroareas', MultiSelect, dict(collection=res['macroareas'])),
        ('doctypes', MultiSelect, dict(collection=res['doctypes'])),
    ]:
        res['ms'][name] = cls(request, name, 'ms' + name, **kw)

    res['params'], reqparams = get_params(request.params, **res)
    res['refs'] = getRefs(res['params'])

    if res['refs']:
        res['dt'] = Refs(request, Source, cq=1, **reqparams)

    fmt = request.params.get('format')
    if fmt:
        db = bibtex.Database([ref.bibtex() for ref in res['refs']])
        for name, adapter in request.registry.getAdapters([db], IRepresentation):
            if name == fmt:
                return adapter.render_to_response(db, request)
        return HTTPNotAcceptable()

    return res


def redirect_languoid_xhtml(req):
    return HTTPMovedPermanently(location=req.route_url('language', id=req.matchdict['id']))


def redirect_reference_xhtml(req):
    return HTTPMovedPermanently(location=req.route_url('source', id=req.matchdict['id']))

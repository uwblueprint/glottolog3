import json
import transaction
from collections import OrderedDict
from itertools import groupby
from unidecode import unidecode

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
    Language, LanguageIdentifier, Identifier, IdentifierType,
)

from glottolog3.models import (
    Languoid, LanguoidSchema, LanguoidStatus, LanguoidLevel, Macroarea, Doctype,
    IdentifierSchema, Refprovider, TreeClosureTable, BOOKKEEPING,
)
from glottolog3.models import GLOTTOCODE_PATTERN

# ENDPOINTS ADDED BY BLUEPRINT
def identifier_score(identifier, term):
    # sorting key method that will return a lower rank for greater similarity
    lower_id = unidecode(identifier.lower())
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
    whole = request.params.get('whole', "False")
    multilingual = request.params.get('multilingual', "True")

    MIN_QUERY_LEN = 3

    if not term:
        query = None
    elif len(term) < MIN_QUERY_LEN:
        return [{'message': 'Query must be at least {} characters.'.format(MIN_QUERY_LEN)}]
    elif len(term) == 8 and GLOTTOCODE_PATTERN.match(term):
        query = query.filter(Languoid.id == term)
        kind = 'Glottocode'
    else:
        # list of criteria to search languoids by
        filters = []
        ul_iname = func.unaccent(func.lower(Identifier.name))
        ul_name = func.unaccent(term)
        if whole.lower() == 'true':
            filters.append(ul_iname == ul_name)
        else:
            filters.append(ul_iname.contains(ul_name))
        if multilingual.lower() == 'false':
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
    ordered_results = OrderedDict(sorted(
        mapped_results.items(),
        key=lambda x: (best_identifier_score(x[1],term), x[0].name)
    ))

    return [{
        'name': k.name,
        'glottocode': k.id,
        'iso': k.hid if k.hid else '',
        'level': k.level.name,
        'matched_identifiers': sorted(
            set([i.Identifier.name for i in v]),
            key=lambda x: identifier_score(x, term)
        )  if kind != 'Glottocode' else [],
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

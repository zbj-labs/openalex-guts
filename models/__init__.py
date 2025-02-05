from sqlalchemy.orm import selectinload
from sqlalchemy import orm
from sqlalchemy.sql.expression import func

from app import db

from models.abstract import Abstract
from models.author import Author
from models.author_orcid import AuthorOrcid
from models.orcid import Orcid
from models.citation import Citation
from models.concept import Concept
from models.author_alternative_name import AuthorAlternativeName
from models.author_concept import AuthorConcept
from models.institution import Institution
from models.venue import Venue
from models.location import Location
from models.mesh import Mesh
from models.record import Record
from models.unpaywall import Unpaywall
from models.work import Work
from models.affiliation import Affiliation
from models.work_concept import WorkConcept
from models.work_concept import WorkConceptFull
from models.ror import Ror
from models.work_extra_id import WorkExtraIds
from models.counts_by_year import AuthorCountsByYear,ConceptCountsByYear, InstitutionCountsByYear, VenueCountsByYear, WorkCountsByYear
from models.concept_ancestor import ConceptAncestor
from models.work_related_work import WorkRelatedWork

# relationships without association tables
Work.mesh = db.relationship("Mesh", lazy='selectin', backref="work")
Work.references = db.relationship("Citation", lazy='selectin', backref="work")
Work.locations = db.relationship("Location", lazy='selectin', backref="work")
Work.abstract = db.relationship("Abstract", lazy='selectin', backref="work", uselist=False)
Work.journal = db.relationship("Venue", lazy='selectin', backref="work", uselist=False)
Work.extra_ids = db.relationship("WorkExtraIds", lazy='selectin', backref="work")
Work.related_works = db.relationship("WorkRelatedWork", lazy='selectin', backref="work")
Work.records = db.relationship("Record", lazy='selectin', backref="work")  # normally don't get, just for mint

# relationships with association tables
Work.affiliations = db.relationship("Affiliation", lazy='selectin', backref="work")
Work.concepts = db.relationship("WorkConcept", lazy='selectin', backref="work")

Affiliation.author = db.relationship("Author")
Affiliation.institution = db.relationship("Institution")

Institution.ror = db.relationship("Ror", uselist=False)
Author.orcids = db.relationship("AuthorOrcid", backref="author")
AuthorOrcid.orcid_data = db.relationship("Orcid", uselist=False)
Author.last_known_institution = db.relationship("Institution")
Author.alternative_names = db.relationship("AuthorAlternativeName")
Author.author_concepts = db.relationship("AuthorConcept")

# Concept.works = db.relationship("WorkConcept", lazy='selectin', backref="concept", uselist=False)
WorkConcept.concept = db.relationship("Concept", lazy='selectin', backref="work_concept", uselist=False)

Author.counts_by_year = db.relationship("AuthorCountsByYear", lazy='selectin', backref="work")
Concept.counts_by_year = db.relationship("ConceptCountsByYear", lazy='selectin', backref="work")
Institution.counts_by_year = db.relationship("InstitutionCountsByYear", lazy='selectin', backref="work")
Venue.counts_by_year = db.relationship("VenueCountsByYear", lazy='selectin', backref="work")
Work.counts_by_year = db.relationship("WorkCountsByYear", lazy='selectin', backref="work")

Record.journals = db.relationship("Venue", lazy='selectin', uselist=True)  # needs to be a list for now because some duplicate issn_ls in mid.journal still alas
Record.unpaywall = db.relationship("Unpaywall", lazy='selectin', uselist=False)

def author_from_id(author_id):
    return Author.query.filter(Author.author_id==author_id).first()

def openalex_id_from_orcid(orcid):
    author_id = db.session.query(AuthorOrcid.author_id).filter(AuthorOrcid.orcid == orcid).limit(1).scalar()
    return f"A{author_id}" if author_id else None

def concept_from_id(concept_id):
    return Concept.query.filter(Concept.field_of_study_id==concept_id).first()

def concept_from_name(name):
    return Concept.query.filter(Concept.display_name.ilike(f'{name}')).order_by(func.length(Concept.display_name)).first()

def institution_from_id(institution_id):
    return Institution.query.filter(Institution.affiliation_id==institution_id).first()

def openalex_id_from_ror(ror_id):
    affiliation_id = db.session.query(Institution.affiliation_id).filter(Institution.ror_id==ror_id).order_by(Institution.citation_count.desc()).limit(1).scalar()
    print(f"I{affiliation_id}")
    return f"I{affiliation_id}" if affiliation_id else None

def journal_from_id(journal_id):
    return Venue.query.filter(Venue.journal_id == journal_id).first()

def openalex_id_from_issn(issn):
    journal_id = db.session.query(Venue.journal_id).filter(Venue.issns.ilike(f'%{issn}%')).order_by(Venue.citation_count.desc()).limit(1).scalar()
    return f"V{journal_id}" if journal_id else None

def openalex_id_from_wikidata(wikidata):
    concept_id = db.session.query(Concept.field_of_study_id).filter(Concept.wikidata_id.ilike(f'%{wikidata}')).limit(1).scalar()
    return f"C{concept_id}" if concept_id else None

def record_from_id(record_id):
    return Record.query.filter(Record.id==record_id).first()

def short_openalex_id(long_openalex_id):
    return long_openalex_id.replace("https://openalex.org/", "")

def single_work_query():
    return db.session.query(Work).options(
         selectinload(Work.locations),
         selectinload(Work.journal),
         selectinload(Work.references),
         selectinload(Work.mesh),
         selectinload(Work.counts_by_year),
         selectinload(Work.abstract),
         selectinload(Work.extra_ids),
         selectinload(Work.related_works),
         selectinload(Work.affiliations).selectinload(Affiliation.author).selectinload(Author.orcids),
         selectinload(Work.affiliations).selectinload(Affiliation.institution).selectinload(Institution.ror),
         selectinload(Work.concepts).selectinload(WorkConcept.concept),
         orm.Load(Work).raiseload('*'))

def work_from_id(work_id):
    my_query = single_work_query()
    return my_query.filter(Work.paper_id==work_id).first()

def openalex_id_from_doi(doi):
    paper_id = db.session.query(Work.paper_id).filter(Work.doi_lower == doi).limit(1).scalar()
    return f"W{paper_id}" if paper_id else None

def openalex_id_from_pmid(pmid):
    pmid_attribute_type = 2
    paper_id = db.session.query(WorkExtraIds.paper_id).filter(WorkExtraIds.attribute_type==pmid_attribute_type, WorkExtraIds.attribute_value==pmid).limit(1).scalar()
    return f"W{paper_id}" if paper_id else None


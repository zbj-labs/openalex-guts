from cached_property import cached_property
from sqlalchemy import text
import json

from app import db


# truncate mid.author
# insert into mid.author (select * from legacy.mag_main_authors)
# update mid.author set display_name=replace(display_name, '\t', '') where display_name ~ '\t';

def as_author_openalex_id(id):
    from app import API_HOST
    return f"{API_HOST}/A{id}"

class Author(db.Model):
    __table_args__ = {'schema': 'mid'}
    __tablename__ = "author"

    author_id = db.Column(db.BigInteger, primary_key=True)
    display_name = db.Column(db.Text)
    last_known_affiliation_id = db.Column(db.Numeric, db.ForeignKey("mid.institution.affiliation_id"))
    paper_count = db.Column(db.Numeric)
    citation_count = db.Column(db.Numeric)
    created_date = db.Column(db.DateTime)
    updated_date = db.Column(db.DateTime)

    @property
    def last_known_institution_id(self):
        return self.last_known_affiliation_id

    @property
    def openalex_id(self):
        return as_author_openalex_id(self.author_id)

    @property
    def last_known_institution_api_url(self):
        if not self.last_known_affiliation_id:
            return None
        return f"http://localhost:5007/institution/id/{self.last_known_affiliation_id}"

    @property
    def orcid(self):
        if not self.orcids:
            return None
        return sorted(self.orcids, key=lambda x: x.orcid)[0].orcid

    @property
    def orcid_url(self):
        if not self.orcid:
            return None
        return "https://orcid.org/{}".format(self.orcid)

    @cached_property
    def papers(self):
        q = "select paper_id from mid.affiliation where author_id = :author_id;"
        rows = db.session.execute(text(q), {"author_id": self.author_id}).fetchall()
        paper_ids = [row[0] for row in rows]
        return paper_ids

    @cached_property
    def citations(self):
        q = """select citation.paper_id as cited_paper_id 
            from mid.affiliation affil
            join mid.citation citation on affil.paper_id=citation.paper_reference_id
            where author_id = :author_id;"""
        rows = db.session.execute(text(q), {"author_id": self.author_id}).fetchall()
        cited_paper_ids = [row[0] for row in rows]
        return cited_paper_ids

    @cached_property
    def all_institutions(self):
        q = """select distinct institution.affiliation_id
            from mid.affiliation affil
            join mid.institution institution on affil.affiliation_id=institution.affiliation_id
            where author_id = :author_id;"""
        rows = db.session.execute(text(q), {"author_id": self.author_id}).fetchall()
        response = list(set([row[0] for row in rows]))
        return response

    @cached_property
    def alternative_names(self):
        q = """
        select attribute_value
        from legacy.mag_main_author_extended_attributes
        WHERE author_id = :author_id
        """
        rows = db.session.execute(text(q), {"author_id": self.author_id}).fetchall()
        response = [row[0] for row in rows]

        # add what we get from orcid
        if self.orcid_data_person:
            try:
                other_name_dicts = self.orcid_data_person["other-names"]["other-name"]
                other_name_dicts = sorted(other_name_dicts, key=lambda x: x["display-index"])
                response += [name["content"] for name in other_name_dicts if name["content"] not in other_name_dicts]
            except TypeError:
                pass
        return response

    @cached_property
    def scopus_url(self):
        if not self.orcid_data_person:
            return None
        for key, value in self.orcid_data_person["external-identifiers"].items():
            if key=="external-identifier" and value:
                for identifier in value:
                    if identifier["external-id-type"] == 'Scopus Author ID':
                        return identifier["external-id-url"]["value"]
        return None

    @cached_property
    def twitter_url(self):
        if not self.orcid_data_person:
            return None
        for key, value in self.orcid_data_person["researcher-urls"].items():
            if key=="researcher-url" and value:
                for identifier in value:
                    if identifier["url-name"] == 'twitter':
                        return identifier["url"]["value"]
        return None


    @cached_property
    def wikipedia_url(self):
        if not self.orcid_data_person:
            return None
        for key, value in self.orcid_data_person["researcher-urls"].items():
            if key=="researcher-url" and value:
                for identifier in value:
                    if identifier["url-name"] == 'Wikipedia Entry':
                        return identifier["url"]["value"]
        return None

    @cached_property
    def orcid_data_person(self):
        if not self.orcid:
            return None

        q = """
        select api_json
        from orcid_raw_from_s3
        WHERE api_json."orcid-identifier".path::text = :orcid
        """
        row = db.session.execute(text(q), {"orcid": self.orcid}).first()
        if row:
            my_data = json.loads(row[0])
            return my_data.get("person", None)
        return None

    @cached_property
    def orcid_data_works(self):
        if not self.orcid:
            return None

        q = """
        select api_json
        from orcid_raw_from_s3
        WHERE api_json."orcid-identifier".path::text = :orcid
        """
        row = db.session.execute(text(q), {"orcid": self.orcid}).first()
        if row:
            my_data = json.loads(row[0])
            return my_data.get("works", None)
        return None

    @cached_property
    def concepts(self):
        from models.concept import as_concept_openalex_id

        q = """
            select ancestor_id as id, ancestor_name as display_name, ancestor_level as level, round(100 * count(distinct affil.paper_id)/author.paper_count::float, 1) as score
            from mid.author author
            join mid.affiliation affil on affil.author_id=author.author_id
            join mid.work_concept wc on wc.paper_id=affil.paper_id
            join mid.concept_self_and_ancestors_view ancestors on ancestors.id=wc.field_of_study
            where author.author_id=:author_id
            group by ancestor_id, ancestor_name, ancestor_level, author.paper_count
            order by score desc"""
        rows = db.session.execute(text(q), {"author_id": self.author_id}).fetchall()
        response = [dict(row) for row in rows if row["score"] > 20]
        for row in response:
            row["id"] = as_concept_openalex_id(row["id"])
        return response


    def to_dict(self, return_level="full"):
        response = {
                "id": self.openalex_id,
                "display_name": self.display_name,
                "orcid": self.orcid_url,
              }
        if return_level == "full":
            response.update({
                "display_name_alternatives": self.alternative_names,
                "scopus_url": self.scopus_url,
                "twitter_url": self.twitter_url,
                "wikipedia_url": self.wikipedia_url,
                "works_count": self.paper_count,
                "cited_by_count": self.citation_count,
                # "orcid_data_person": self.orcid_data_person,
                "last_known_institution": self.last_known_institution.to_dict("minimum") if self.last_known_institution else None,
                "concepts": self.concepts,
                "works_api_url": f"https://elastic.api.openalex.org/works?filter=author_id:{self.author_id}&details=true",
                "updated_date": self.updated_date
            })
        return response

    def __repr__(self):
        return "<Author ( {} ) {}>".format(self.openalex_id, self.display_name)



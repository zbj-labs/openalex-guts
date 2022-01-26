from cached_property import cached_property
from sqlalchemy import text
from sqlalchemy import orm
from sqlalchemy.orm import selectinload
import datetime
from collections import defaultdict
import requests
import os
import json

import shortuuid
import random


from app import db
from app import MAX_MAG_ID
from app import get_apiurl_from_openalex_url
from util import normalize_title
from util import jsonify_fast_no_sort_raw
from util import normalize_simple


# truncate mid.work
# insert into mid.work (select * from legacy.mag_main_papers)
# update mid.work set original_title=replace(original_title, '\\\\/', '/');

# update work set match_title = f_matching_string(original_title)

def as_work_openalex_id(id):
    from app import API_HOST
    return f"{API_HOST}/W{id}"

def call_sagemaker_bulk_lookup_new_work_concepts(rows):
    insert_dicts = []
    data_list = []
    for row in rows:
        data_list += [{
            "title": row["paper_title"].lower(),
            "doc_type": row["doc_type"],
            "journal": row["journal_title"].lower() if row["journal_title"] else None
        }]

    class ConceptLookupResponse:
        def get_insert_dict_fieldnames(self, table_name):
            return ["paper_id", "field_of_study", "score", "algorithm_version"]
        pass

    api_key = os.getenv("SAGEMAKER_API_KEY")
    headers = {"X-API-Key": api_key}
    api_url = "https://4rwjth9jek.execute-api.us-east-1.amazonaws.com/api/"
    r = requests.post(api_url, json=json.dumps(data_list), headers=headers)
    if r.status_code != 200:
        print(f"error: status code {r}")
        return []

    api_json = r.json()
    for row, api_dict in zip(rows, api_json):
        if api_dict["tags"] != []:
            for i, concept_name in enumerate(api_dict["tags"]):
                insert_dicts += [{"mid.work_concept": {"paper_id": row["paper_id"],
                                                       "field_of_study": api_dict["tag_ids"][i],
                                                       "score": api_dict["scores"][i],
                                                       "algorithm_version": 2}}]
        else:
            matching_ids = []
            insert_dicts += [{"mid.work_concept": {"paper_id": row["paper_id"],
                                                       "field_of_study": None,
                                                       "score": None,
                                                       "algorithm_version": 2}}]

    response = ConceptLookupResponse()
    response.insert_dicts = insert_dicts
    return [response]


class Work(db.Model):
    __table_args__ = {'schema': 'mid'}
    __tablename__ = "work"

    # id = db.Column(db.BigInteger)
    paper_id = db.Column(db.BigInteger, primary_key=True)
    doi = db.Column(db.Text)
    doc_type = db.Column(db.Text)
    paper_title = db.Column(db.Text)
    original_title = db.Column(db.Text)
    year = db.Column(db.Numeric)
    publication_date = db.Column(db.DateTime)
    online_date = db.Column(db.DateTime)
    publisher = db.Column(db.Text)
    journal_id = db.Column(db.BigInteger)
    volume = db.Column(db.Text)
    issue = db.Column(db.Text)
    first_page = db.Column(db.Text)
    last_page = db.Column(db.Text)
    reference_count = db.Column(db.Numeric)
    citation_count = db.Column(db.Numeric)
    estimated_citation = db.Column(db.Numeric)
    created_date = db.Column(db.DateTime)
    updated_date = db.Column(db.DateTime)
    doi_lower = db.Column(db.Text)
    doc_sub_types = db.Column(db.Text)
    original_venue = db.Column(db.Text)
    genre = db.Column(db.Text)
    is_paratext = db.Column(db.Boolean)
    oa_status = db.Column(db.Text)
    best_url = db.Column(db.Text)
    best_free_url = db.Column(db.Text)
    best_free_version = db.Column(db.Text)

    match_title = db.Column(db.Text)

    started = db.Column(db.DateTime)
    finished = db.Column(db.DateTime)
    started_label = db.Column(db.Text)


    def __init__(self, **kwargs):
        self.created = datetime.datetime.utcnow().isoformat()
        self.updated = self.created
        super(Work, self).__init__(**kwargs)

    @property
    def id(self):
        return self.paper_id

    @property
    def cited_by_api_url(self):
        return f"https://api.openalex.org/works?filter=cites:{self.openalex_id_short}"

    @property
    def openalex_id(self):
        return as_work_openalex_id(self.paper_id)

    @property
    def openalex_id_short(self):
        from models import short_openalex_id
        return short_openalex_id(self.openalex_id)

    @property
    def openalex_api_url(self):
        return get_apiurl_from_openalex_url(self.openalex_id)

    def new_work_concepts(self):
        self.insert_dicts = []
        api_key = os.getenv("SAGEMAKER_API_KEY")
        data = {
            "title": self.work_title.lower(),
            "doc_type": self.doc_type,
            "journal": self.journal.display_name.lower() if self.journal else None
        }
        headers = {"X-API-Key": api_key}
        api_url = "https://4rwjth9jek.execute-api.us-east-1.amazonaws.com/api/"
        r = requests.post(api_url, json=json.dumps([data]), headers=headers)
        response_json = r.json()
        concept_names = response_json[0]["tags"]
        if concept_names:
            # concept_names_string = "({})".format(", ".join(["'{}'".format(concept_name) for concept_name in concept_names]))
            # q = """
            # select field_of_study_id, display_name
            # from mid.concept
            # where lower(display_name) in {concept_names_string}
            # """.format(concept_names_string=concept_names_string)
            # matching_concepts = db.session.execute(text(q)).all()
            # print(f"concepts that match: {matching_concepts}")
            # matching_ids = [concept[0] for concept in matching_concepts]
            for i, concept_name in enumerate(concept_names):
                self.insert_dicts += [{"mid.new_work_concepts": "({paper_id}, '{concept_name_lower}', {concept_id}, {score}, '{updated}')".format(
                                      paper_id=self.id,
                                      concept_name_lower=response_json[0]["tags"][i],
                                      concept_id=response_json[0]["tag_ids"][i],
                                      score=response_json[0]["scores"][i],
                                      updated=datetime.datetime.utcnow().isoformat(),
                                    )}]
        else:
            matching_ids = []
            self.insert_dicts += [{"mid.new_work_concepts": "({paper_id}, '{concept_name_lower}', {concept_id}, {score}, '{updated}')".format(
                                      paper_id=self.id,
                                      concept_name_lower=None,
                                      concept_id="NULL",
                                      score="NULL",
                                      updated=datetime.datetime.utcnow().isoformat(),
                                    )}]


    def set_fields_from_record(self, record):
        from sqlalchemy import select
        from sqlalchemy import func
        from util import clean_doi

        # ideally this would also handle non-normalized journals but that info isn't in recordthresher yet
        self.original_title = record.title
        self.paper_title = normalize_simple(record.title, remove_articles=False, remove_spaces=False)
        self.doc_type = record.normalized_doc_type
        self.created_date = datetime.datetime.utcnow().isoformat()
        self.updated_date = datetime.datetime.utcnow().isoformat()
        self.match_title = record.match_title

        self.original_venue = record.venue_name
        if record.journal:
            self.original_venue = record.journal.display_name  # overwrite record.venue_name if have a normalized name
            self.publisher = record.journal.publisher
            self.journal_id = record.journal.journal_id

        self.doi = record.doi
        self.doi_lower = clean_doi(self.doi, return_none_if_error=True)
        self.publication_date = record.published_date.isoformat()[0:10]
        self.year = int(record.published_date.isoformat()[0:4]) if record.published_date else None
        # self.online_date = record.published_date

        self.volume = record.volume
        self.issue = record.issue
        self.first_page = record.first_page
        self.last_page = record.last_page
        self.doc_sub_types = "Retracted" if record.is_retracted else None
        self.genre = record.normalized_type
        self.best_url = record.record_webpage_url

        if record.unpaywall:
            self.is_paratext = record.unpaywall.is_paratext
            self.oa_status = record.unpaywall.oa_status
            self.best_free_url = record.unpaywall.best_oa_location_url
            self.best_free_version = record.unpaywall.best_oa_location_version



    def refresh(self):
        from models import Record

        # - [x] what should be a work
        # - [x] get work IDs minted
        # - [x] concepts for those work IDs
        # all handled via SQL for now
        #
        # - [ ] other easy things we can get from recordthresher
        # - [ ] other things we can figure out
        # - [ ] mesh
        # - [ ] abstract
        # - [ ] additional ids
        # - [ ] other things we can get from unpaywall
        #     - [ ] base
        #     - [ ] location
        # - [ ] complicated
        #     - [ ] citations
        #     - [ ] authors (after citations)
        #     - [ ] institutions
        #     - [ ] last known institutions
        # - [ ] related papers (after author stuff)
        # - [ ] update citation counts for everything

        # select count(distinct work_id) from mid.work_match_recordthresher where work_id > 4205086888

        print(f"refreshing! {self.id}")
        self.started = datetime.datetime.utcnow().isoformat()
        self.finished = datetime.datetime.utcnow().isoformat()

        # go through them with oldest first, and least reliable record type to most reliable, overwriting
        records = sorted(self.records, key=lambda x: x.updated, reverse=True)

        print(f"my records: {records}")

        for record in records:
            if record.record_type == "pmh_record":
                self.set_fields_from_record(record)
        for record in records:
            if record.record_type == "pubmed_record":
                self.set_fields_from_record(record)
        for record in records:
            if record.record_type == "crossref_doi":
                self.set_fields_from_record(record)

        self.started_label = "new from match"

        insert_dict = {}
        for key in self.get_insert_dict_fieldnames("mid.work"):
            insert_dict[key] = getattr(self, key)
        self.insert_dicts = [{"mid.work": insert_dict}]

        print(f"done! {self.id}")

        # insert into mid.citation (paper_id, paper_reference_id)
        # (select parse.paper_id, work.paper_id as paper_reference_id
        # from util.parse_citation_view parse
        # join mid.work work on work.doi_lower = parse.referenced_doi
        # )
        #
        # UPDATE temp_candidate_authors set matching_author_id = t1.my_author_id
        # FROM
        # (
        #     SELECT 1 + 4202861942 + row_number() over (partition by 1) AS my_author_id, paper_id, author_sequence_number
        #     FROM temp_candidate_authors
        # ) AS t1
        # WHERE temp_candidate_authors.paper_id = t1.paper_id
        # and temp_candidate_authors.author_sequence_number = t1.author_sequence_number
        # and temp_candidate_authors.matching_author_id is null
        #
        # -- related_work

    @cached_property
    def is_retracted(self):
        if self.doc_sub_types != None:
            return True
        return False

    @cached_property
    def affiliations_sorted(self):
        return sorted(self.affiliations, key=lambda x: x.author_sequence_number)

    @cached_property
    def mesh_sorted(self):
        # sort so major topics at the top and the rest is alphabetical
        return sorted(self.mesh, key=lambda x: (not x.is_major_topic, x.descriptor_name), reverse=False)

    @cached_property
    def affiliations_list(self):
        affiliations = [affiliation for affiliation in self.affiliations_sorted[:100]]
        if not affiliations:
            return []

        # it seems like sometimes there are 0s and sometimes 1st, so figure out the minimum
        first_author_sequence_number = min([affil.author_sequence_number for affil in affiliations])
        last_author_sequence_number = max([affil.author_sequence_number for affil in affiliations])
        affiliation_dict = defaultdict(list)
        for affil in affiliations:
            affil.author_position = "middle"
            if affil.author_sequence_number == first_author_sequence_number:
                affil.author_position = "first"
            elif affil.author_sequence_number == last_author_sequence_number:
                affil.author_position = "last"
            affiliation_dict[affil.author_sequence_number] += [affil.to_dict("minimum")]
        response = []
        for seq, affil_list in affiliation_dict.items():
            institution_list = [a["institution"] for a in affil_list]
            if institution_list == [{}]:
                institution_list = []
            response_dict = {"author_position": affil_list[0]["author_position"],
                             "author": affil_list[0]["author"],
                             "institutions": institution_list,
                             "raw_affiliation_string": affil_list[0]["raw_affiliation_string"]
                     }
            response.append(response_dict)
        return response

    @property
    def concepts_sorted(self):
        return sorted(self.concepts, key=lambda x: x.score, reverse=True)

    @property
    def locations_sorted(self):
        return sorted(self.locations, key=lambda x: x.score, reverse=True)

    @property
    def mag_publisher(self):
        return self.publisher

    @property
    def work_title(self):
        return self.original_title

    @property
    def work_id(self):
        return self.paper_id

    @property
    def doi_url(self):
        if not self.doi:
            return None
        return "https://doi.org/{}".format(self.doi.lower())

    @cached_property
    def is_oa(self):
        if self.best_free_url != None:
            return True
        if self.oa_status != "closed":
            return True
        return False

    @cached_property
    def display_genre(self):
        if self.genre:
            return self.genre
        if self.doc_type:
            lookup_mag_to_crossref_type = {
                "Journal": "journal-article",
                "Thesis": "dissertation",
                "Conference": "proceedings-article",
                "Repository": "posted-content",
                "Book": "book",
                "BookChapter": "book-chapter",
                "Dataset": "dataset",
            }
            return lookup_mag_to_crossref_type[self.doc_type]
        return None

    @cached_property
    def references_list(self):
        import models

        reference_paper_ids = [as_work_openalex_id(reference.paper_reference_id) for reference in self.references]
        return reference_paper_ids

        # objs = db.session.query(Work).options(
        #      selectinload(Work.journal).selectinload(models.Venue.journalsdb),
        #      selectinload(Work.extra_ids),
        #      selectinload(Work.affiliations).selectinload(models.Affiliation.author).selectinload(models.Author.orcids),
        #      selectinload(Work.affiliations).selectinload(models.Affiliation.institution).selectinload(models.Institution.ror),
        #      orm.Load(Work).raiseload('*')).filter(Work.paper_id.in_(reference_paper_ids)).all()
        # response = [obj.to_dict("minimum") for obj in objs]
        # return response

    def store(self):
        VERSION_STRING = "save for second release"

        # print("processing work! {}".format(self.id))
        self.json_save = jsonify_fast_no_sort_raw(self.to_dict("store"))

        # has to match order of get_insert_dict_fieldnames
        if len(self.json_save) > 65000:
            print("Error: json_save_escaped too long for paper_id {}, skipping".format(self.openalex_id))
            self.json_save = None
        updated = datetime.datetime.utcnow().isoformat()
        self.insert_dicts = [{"mid.json_works": {"id": self.paper_id, "updated": updated, "json_save": self.json_save, "version": VERSION_STRING}}]

        # print(self.insert_dicts)
        # print(self.json_save[0:100])

    def get_insert_dict_fieldnames(self, table_name=None):
        lookup = {
            "mid.json_works": ["id", "updated", "json_save", "version"],
            "mid.work_concept": ["paper_id", "field_of_study", "score", "algorithm_version"],
            "mid.work": """
                        paper_id
                        doi
                        doc_type
                        paper_title
                        original_title
                        year
                        publication_date
                        online_date
                        publisher
                        journal_id
                        volume
                        issue
                        first_page
                        last_page
                        created_date
                        updated_date
                        doi_lower
                        doc_sub_types
                        original_venue
                        genre
                        is_paratext
                        oa_status
                        best_url
                        best_free_url
                        best_free_version
                        match_title
                        started_label""".split()
        }
        if table_name:
            return lookup[table_name]
        return lookup


    @cached_property
    def display_counts_by_year(self):
        response_dict = {}
        for count_row in self.counts_by_year:
            response_dict[count_row.year] = {"year": count_row.year, "cited_by_count": 0}
        for count_row in self.counts_by_year:
            if count_row.type == "citation_count":
                response_dict[count_row.year]["cited_by_count"] = count_row.n

        my_dicts = [counts for counts in response_dict.values() if counts["year"] and counts["year"] >= 2012]
        response = sorted(my_dicts, key=lambda x: x["year"], reverse=True)
        return response

    @property
    def host_venue_details_dict(self):
        # should match the extra stuff put out in locations.to_dict()
        matching_location = None
        url = None
        for location in self.locations_sorted:
            if "doi.org/" in location.source_url and not matching_location:
                matching_location = location
            elif not matching_location:
                if location.host_type == "publisher":
                    matching_location = location
        if self.locations_sorted and (not matching_location):
            matching_location = self.locations_sorted[0]

        if self.best_url:
            url = self.best_url
        elif matching_location:
            url = matching_location.source_url

        type = None
        if matching_location and matching_location.host_type != None:
            type = matching_location.host_type
        elif self.journal and self.journal.issn_l:
            type = "publisher"
        elif url and "doi.org/" in url:
            type = "publisher"

        version = matching_location.version if matching_location else None
        license = matching_location.display_license if matching_location else None

        is_oa = None
        if matching_location and matching_location.is_oa != None:
            is_oa = matching_location.is_oa
        elif self.is_oa == False:
            is_oa = False
        elif self.oa_status == "gold":
            is_oa = True
            version = "publishedVersion"

        response = {
            "type": type,
            "url": url,
            "is_oa": is_oa,
            "version": version,
            "license": license
        }
        return response

    def to_dict(self, return_level="full"):
        from models import Venue

        response = {
            "id": self.openalex_id,
            "doi": self.doi_url,
            "display_name": self.work_title,
            "title": self.work_title,
            "publication_year": self.year,
            "publication_date": self.publication_date,
            "ids": {
                "openalex": self.openalex_id,
                "doi": self.doi_url,
                "pmid": None, #filled in below
                "mag": self.paper_id if self.paper_id < MAX_MAG_ID else None
            },
            "host_venue": self.journal.to_dict("minimum") if self.journal else Venue().to_dict_null_minimum(),
            "type": self.display_genre,
            "open_access": {
                "is_oa": self.is_oa,
                "oa_status": self.oa_status,
                "oa_url": self.best_free_url,
            },
            "authorships": self.affiliations_list,
        }
        response["host_venue"].update(self.host_venue_details_dict)
        response["host_venue"]["display_name"] = response["host_venue"]["display_name"] if response["host_venue"]["display_name"] else self.original_venue
        response["host_venue"]["publisher"] = response["host_venue"]["publisher"] if response["host_venue"]["publisher"] else self.publisher
        if self.extra_ids:
            for extra_id in self.extra_ids:
                response["ids"][extra_id.id_type] = extra_id.url

        if return_level in ("full", "store"):
            response.update({
                # "doc_type": self.doc_type,
                "cited_by_count": self.citation_count,
                "biblio": {
                    "volume": self.volume,
                    "issue": self.issue,
                    "first_page": self.first_page,
                    "last_page": self.last_page
                },
                "is_retracted": self.is_retracted,
                "is_paratext": self.is_paratext,
                "concepts": [concept.to_dict("minimum") for concept in self.concepts_sorted],
                "mesh": [mesh.to_dict("minimum") for mesh in self.mesh_sorted],
                "alternate_host_venues": [location.to_dict("minimum") for location in self.locations_sorted if location.include_in_alternative],
                "referenced_works": self.references_list,
                "related_works": [as_work_openalex_id(related.recommended_paper_id) for related in self.related_works]
                })
            if return_level == "full":
                response["abstract_inverted_index"] = self.abstract.to_dict("minimum") if self.abstract else None
            response["counts_by_year"] = self.display_counts_by_year
            response["cited_by_api_url"] = self.cited_by_api_url
            response["updated_date"] = self.updated_date

        # only include non-null IDs
        for id_type in list(response["ids"].keys()):
            if response["ids"][id_type] == None:
                del response["ids"][id_type]

        return response


    def __repr__(self):
        return "<Work ( {} ) {} '{}...'>".format(self.openalex_api_url, self.doi, self.original_title[0:20] if self.original_title else None)





import json

from app import db

# insert into mid.abstract (paper_id, indexed_abstract) (select paper_id, inverted_index_json from legacy.mag_nlp_abstracts_inverted);
# update mid.abstract set indexed_abstract=replace(indexed_abstract, '\\u0000', '') where indexed_abstract ~ '\\u0000';

class Abstract(db.Model):
    __table_args__ = {'schema': 'mid'}
    __tablename__ = "abstract"

    paper_id = db.Column(db.BigInteger, db.ForeignKey("mid.work.paper_id"), primary_key=True)
    indexed_abstract = db.Column(db.Text)

    def to_dict(self, return_level="full"):
        indexed_abstract_dict = json.loads(self.indexed_abstract)
        return indexed_abstract_dict["InvertedIndex"]

    def __repr__(self):
        return "<Abstract ( {} ) {}>".format(self.paper_id, self.indexed_abstract[0:100])



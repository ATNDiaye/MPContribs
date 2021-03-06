from pymatgen.matproj.snl import Author
from pymongo import MongoClient
from monty.serialization import loadfn
import json, os, logging
import pandas as pd
import matplotlib.pyplot as plt
pd.options.display.mpl_style = 'default'
import plotly.plotly as py
from plotly.graph_objs import *

class MPContributionsBuilder():
    """build user contributions from `mg_core_*.contributions`"""
    def __init__(self, db):
        self.contrib_coll = db.contributions
        self.mat_coll = db.materials
        self.pipeline = [
            { '$group': {
                '_id': '$mp_cat_id',
                'num_contribs': { '$sum': 1 },
                'contrib_ids': { '$addToSet': '$contribution_id' }
            }}
        ]

    @classmethod
    def from_config(cls, db_yaml='materials_db_dev.yaml'):
        config = loadfn(os.path.join(os.environ['DB_LOC'], db_yaml))
        client = MongoClient(config['host'], config['port'], j=False)
        db = client[config['db']]
        db.authenticate(config['username'], config['password'])
        return MPContributionsBuilder(db)

    def flatten_dict(self, dd, separator='.', prefix=''):
        """http://stackoverflow.com/a/19647596"""
        return { prefix + separator + k if prefix else k : v
                for kk, vv in dd.items()
                for k, v in self.flatten_dict(vv, separator, kk).items()
               } if isinstance(dd, dict) else { prefix : dd }

    def plot(self, contributor_email, cid):
        """make all plots for contribution_id"""
        plot_contrib = self.contrib_coll.find_one(
            {'contribution_id': cid}, {
                'content.data': 1, 'content.plots': 1,
                '_id': 0, 'collaborators': 1, 'project': 1
            }
        )
        if 'data' not in plot_contrib['content']:
            return None
        author = Author.parse_author(contributor_email)
        project = str(author.name).translate(None, '.').replace(' ','_') \
                if 'project' not in plot_contrib else plot_contrib['project']
        subfld = 'contributed_data.%s.plotly_urls.%d' % (project, cid)
        data = plot_contrib['content']['data']
        df = pd.DataFrame.from_dict(data)
        url_list = list(self.mat_coll.find(
            {subfld: {'$exists': True}},
            {'_id': 0, subfld: 1}
        ))
        urls = []
        if len(url_list) > 0:
            urls = url_list[0]['contributed_data'][project]['plotly_urls'][str(cid)]
        for nplot,plotopts in enumerate(
            plot_contrib['content']['plots'].itervalues()
        ):
            filename = 'test%d_%d' % (cid,nplot)
            fig, ax = plt.subplots(1, 1)
            df.plot(ax=ax, **plotopts)
            if len(urls) == len(plot_contrib['content']['plots']):
                pyfig = py.get_figure(urls[nplot])
                for ti,line in enumerate(ax.get_lines()):
                    pyfig['data'][ti]['x'] = list(line.get_xdata())
                    pyfig['data'][ti]['y'] = list(line.get_ydata())
                py.plot(pyfig, filename=filename, auto_open=False)
            else:
                update = dict(
                    layout=dict(
                        annotations=[dict(text=' ')],
                        showlegend=True,
                        legend=Legend(x=1.05, y=1)
                    ),
                )
                urls.append(py.plot_mpl(
                    fig, filename=filename, auto_open=False,
                    strip_style=True, update=update, resize=True
                ))
        return None if len(url_list) > 0 else urls

    def _reset(self):
        """remove `contributed_data` keys from all documents"""
        logging.info(self.mat_coll.update(
            {'contributed_data': {'$exists': 1}},
            {'$unset': {'contributed_data': 1}},
            multi=True
        ))

    def delete(self, cids):
        """remove contributions"""
        unset_dict = {}
        # TODO: FIX THIS
        # using find during switch from contributor to project, project is known usually
        # also fld and cid will be switching places when DBs are migrated
        # TODO: remove `project` field when no contributions remaining
        for doc in self.mat_coll.find(
            {'contributed_data': {'$exists': 1}},
            {'_id': 0, 'contributed_data': 1}
        ):
            for project,d in doc['contributed_data'].iteritems():
                for fld,dd in d.iteritems():
                    for cid in dd:
                        if int(cid) not in cids: continue
                        key = 'contributed_data.%s.%s.%s' % (project, fld, cid)
                        unset_dict[key] = 1
        self.mat_coll.update(
            {'contributed_data': {'$exists': 1}},
            {'$unset': unset_dict}, multi=True
        )

    def build(self, contributor_email, cids=None):
        """update materials collection with contributed data"""
        # NOTE: this build is only for contributions tagged with mp-id
        # TODO: in general, distinguish mp cat's by format of mp_cat_id
        # TODO check all DB calls, consolidate in aggregation call?
        plot_cids = None
        for doc in self.contrib_coll.aggregate(self.pipeline, cursor={}):
            #if plot_cids is None and doc['num_contribs'] > 2:
            # only make plots for one mp-id due to plotly restrictions
            plot_cids = doc['contrib_ids']
            for cid in doc['contrib_ids']:
                if cids is not None and cid not in cids: continue
                contrib = self.contrib_coll.find_one({'contribution_id': cid})
                if contributor_email not in contrib['collaborators']:
                    raise ValueError(
                        "Build stopped: building contribution {} not"
                        " allowed due to insufficient permissions of {}!"
                        " Ask someone of {} to make you a collaborator on"
                        " contribution {}.".format(
                            cid, contributor_email, contrib['collaborators'], cid
                        ))
                author = Author.parse_author(contributor_email)
                project = str(author.name).translate(None, '.').replace(' ','_') \
                        if 'project' not in contrib else contrib['project']
                logging.info(doc['_id'])
                all_data = {}
                if contrib['content']:
                    all_data.update({
                        'contributed_data.%s.tree_data.%d' % (project, cid): contrib['content'],
                    })
                if 'data' in contrib['content']:
                    table_columns, table_rows = None, None
                    raw_data = contrib['content']['data']
                    if isinstance(raw_data, dict):
                        table_columns = [ { 'title': k } for k in raw_data ]
                        table_rows = [
                            [ str(raw_data[d['title']][row_index]) for d in table_columns ]
                            for row_index in xrange(len(
                                raw_data[table_columns[0]['title']]
                            ))
                        ]
                    elif isinstance(raw_data, list):
                        table_columns = [ { 'title': k } for k in raw_data[0] ]
                        table_rows = [
                            [ str(row[d['title']]) for d in table_columns ]
                            for row in raw_data
                        ]
                    if table_columns is not None:
                        all_data.update({
                            'contributed_data.%s.tables.%d.columns' % (project,cid): table_columns,
                            'contributed_data.%s.tables.%d.rows' % (project,cid): table_rows,
                        })
                logging.info(self.mat_coll.update(
                    {'task_id': doc['_id']}, { '$set': all_data }
                ))
                if plot_cids is not None and cid in plot_cids:
                    plotly_urls = self.plot(contributor_email, cid)
                    if plotly_urls is not None:
                        for plotly_url in plotly_urls:
                            logging.info(self.mat_coll.update(
                                {'task_id': doc['_id']}, { '$push': {
                                    'contributed_data.%s.plotly_urls.%d' % (project,cid): plotly_url
                                }}
                            ))

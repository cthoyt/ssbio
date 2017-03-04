import os
import subprocess
import os.path as op
from ssbio import utils
date = utils.Date()

import logging
log = logging.getLogger(__name__)

import pandas as pd


def run_makeblastdb(infile, dbtype, outdir=''):
    """Make the BLAST database for a genome file.

    Args:
        infile (str): path to genome FASTA file
        dbtype (str): "nucl" or "prot" - what format your genome files are in
        outdir (str): path to directory to output database files (default is original folder)

    Returns:
        Paths to BLAST databases.

    """

    # TODO: rewrite using utils function command

    # Output location
    og_dir, name, ext = utils.split_folder_and_path(infile)
    if not outdir:
        outdir = og_dir
    outfile_basename = op.join(outdir, name)

    # Check if BLAST DB was already made
    if dbtype == 'nucl':
        outext = ['.nhr', '.nin', '.nsq']
    elif dbtype == 'prot':
        outext = ['.phr', '.pin', '.psq']
    else:
        raise ValueError('dbtype must be "nucl" or "prot"')
    outfile_all = [outfile_basename + x for x in outext]
    db_made = True
    for f in outfile_all:
        if not op.exists(f):
            db_made = False

    # Run makeblastdb if DB does not exist
    if db_made:
        log.debug('BLAST database already exists at {}'.format(outfile_basename))
        return outfile_all
    else:
        retval = subprocess.call('makeblastdb -in {} -dbtype {} -out {}'.format(infile, dbtype, outfile_basename), shell=True)
        if retval == 0:
            log.debug('Made BLAST database at {}'.format(outfile_basename))
            return outfile_all
        else:
            log.error('Error running makeblastdb, exit code {}'.format(retval))


def run_bidirectional_blast(reference, other_genome, dbtype, outdir=''):
    """BLAST a genome against another, and vice versa.

    This function requires BLAST to be installed, do so by running:
    sudo apt install ncbi-blast+

    Args:
        reference (str): path to "reference" genome, aka your "base strain"
        other_genome (str): path to other genome which will be BLASTed to the reference
        dbtype (str): "nucl" or "prot" - what format your genome files are in
        outdir (str): path to folder where BLAST outputs should be placed

    Returns:
        Paths to BLAST output files.
        (reference_vs_othergenome.out, othergenome_vs_reference.out)

    """

    if dbtype == 'nucl':
        command = 'blastn'
    elif dbtype == 'prot':
        command = 'blastp'
    else:
        raise ValueError('dbtype must be "nucl" or "prot"')

    r_folder, r_name, r_ext = utils.split_folder_and_path(reference)
    g_folder, g_name, g_ext = utils.split_folder_and_path(other_genome)

    # make sure BLAST DBs have been made
    run_makeblastdb(infile=reference, dbtype=dbtype, outdir=r_folder)
    run_makeblastdb(infile=other_genome, dbtype=dbtype, outdir=g_folder)

    # Reference vs genome
    r_vs_g = r_name + '_vs_' + g_name + '_blast.out'
    r_vs_g = op.join(outdir, r_vs_g)
    if op.exists(r_vs_g) and os.stat(r_vs_g).st_size != 0:
        log.debug('{} vs {} BLAST already run'.format(r_name, g_name))
    else:
        cmd = '{} -query {} -db {} -outfmt 6 -out {}'.format(command, reference, op.join(g_folder, g_name), r_vs_g)
        log.debug('Running: {}'.format(cmd))
        retval = subprocess.call(cmd, shell=True)
        if retval == 0:
            log.debug('BLASTed {} vs {}'.format(g_name, r_name))
        else:
            log.error('Error running {}, exit code {}'.format(command, retval))

    # Genome vs reference
    g_vs_r = g_name + '_vs_' + r_name + '_blast.out'
    g_vs_r = op.join(outdir, g_vs_r)
    if op.exists(g_vs_r) and os.stat(g_vs_r).st_size != 0:
        log.debug('{} vs {} BLAST already run'.format(g_name, r_name))
    else:
        cmd = '{} -query {} -db {} -outfmt 6 -out {}'.format(command, other_genome, op.join(r_folder, r_name), g_vs_r)
        log.debug('Running: {}'.format(cmd))
        retval = subprocess.call(cmd, shell=True)
        if retval == 0:
            log.debug('BLASTed {} vs {}'.format(g_name, r_name))
        else:
            log.error('Error running {}, exit code {}'.format(command, retval))

    return r_vs_g, g_vs_r


def calculate_bbh(blast_results_1, blast_results_2, r_name=None, g_name=None, outdir=''):
    """Calculate the best bidirectional BLAST hits (BBH) and save a dataframe of results.

    Args:
        blast_results_1 (str): BLAST results for reference vs. other genome
        blast_results_2 (str): BLAST results for other vs. reference genome
        r_name: Name of reference genome
        g_name: Name of other genome
        outdir: Directory where BLAST results are stored.

    Returns:
        Path to Pandas DataFrame of the BBH results.

    """

    cols = ['gene', 'subject', 'PID', 'alnLength', 'mismatchCount', 'gapOpenCount', 'queryStart', 'queryEnd',
            'subjectStart', 'subjectEnd', 'eVal', 'bitScore']

    if not r_name and not g_name:
        r_name = op.basename(blast_results_1).split('_vs_')[0]
        g_name = op.basename(blast_results_1).split('_vs_')[1].replace('_blast.out', '')

        r_name2 = op.basename(blast_results_2).split('_vs_')[1].replace('_blast.out', '')
        if r_name != r_name2:
            log.warning('{} != {}'.format(r_name, r_name2))

    bbh1 = pd.read_csv(blast_results_1, sep='\t', names=cols)
    bbh2 = pd.read_csv(blast_results_2, sep='\t', names=cols)

    outfile = op.join(outdir, '{}_vs_{}_bbh.csv'.format(r_name, g_name))
    if op.exists(outfile) and os.stat(outfile).st_size != 0:
        log.debug('{} vs {} BLAST BBHs already found at {}'.format(r_name, g_name, outfile))
        return outfile

    out = pd.DataFrame()
    log.debug('Finding BBHs for {} vs. {}'.format(r_name, g_name))

    for g in bbh1[pd.notnull(bbh1.gene)].gene.unique():
        res = bbh1[bbh1.gene == g]
        if len(res) == 0:
            continue
        best_hit = res.ix[res.PID.idxmax()].copy()
        best_gene = best_hit.subject
        res2 = bbh2[bbh2.gene == best_gene]
        if len(res2) == 0:
            continue
        best_hit2 = res2.ix[res2.PID.idxmax()]
        best_gene2 = best_hit2.subject
        if g == best_gene2:
            best_hit['BBH'] = '<=>'
        else:
            best_hit['BBH'] = '->'
        out = pd.concat([out, pd.DataFrame(best_hit).transpose()])

    out.to_csv(outfile)
    log.debug('{} vs {} BLAST BBHs saved at {}'.format(r_name, g_name, outfile))
    return outfile


def create_orthology_matrix(r_name, genome_to_bbh_files, pid_cutoff=80, bitscore_cutoff=0, outname='', outdir=''):
    """Create the orthology matrix of the reference genes to the BBHs in all other_genomes.

    Args:
        r_name (str): name of the reference genome
        genome_to_bbh_files (dict): mapping of genome names to the BBH files
        pid_cutoff (int): Min percent identity between BLAST hits to filter for in the range (0,100)
        bitscore_cutoff: Min bitscore cutoff between BLAST hits to filter for
        outname: Name of output file of orthology matrix
        outdir: Path to output directory

    Returns:
        Path to orthologous genes matrix.

    """
    if outname:
        outfile = op.join(outdir, outname)
    else:
        outfile = op.join(outdir, '{}_orthology.csv'.format(r_name))

    out = pd.DataFrame()

    for g_name, bbh_path in genome_to_bbh_files.items():

        data = pd.read_csv(bbh_path, index_col=0)

        # TODO: adjust to use something else besides 80% PID or just allow what cutoff to use
        data = data[(data.PID > pid_cutoff) & (data.BBH == '<=>')]
        data.index = data.gene

        data2 = data[['subject']]
        if len(out) == 0:
            out = data2
            out = out.rename(columns={'subject': g_name})  # ,'PID':g_name+'_PID'})
        else:
            out = pd.merge(out, data2, left_index=True, right_index=True, how='outer')
            out = out.rename(columns={'subject': g_name})  # ,'PID':g_name+'_PID'})

    out.to_csv(outfile)
    log.debug('{} orthologous genes saved at {}'.format(r_name, outfile))
    return outfile
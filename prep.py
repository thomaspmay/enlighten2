#!/usr/bin/env python3
import argparse
import json
import pdb_utils
import wrappers
import shutil
import utils
import sys
import os

parser = argparse.ArgumentParser(
    description=""
    "Prepares the simulation system by performing the following actions:\n"
    " - ligand parameterisation (with antechamber/prmchk2)\n"
    " - pdb protonation (apart from ligands, they need to "
    "   be protonated already!)\n"
    " - tleap to solvate and write starting parm7/rst7 (top/rst)\n\n"
    "Is meant to be followed by struct.py",
    formatter_class=argparse.RawDescriptionHelpFormatter
)

parser.add_argument("pdb", help="protonated PDB file",
                    type=argparse.FileType())
parser.add_argument("ligand",
                    help="name of the residue to be used as the ligand")
parser.add_argument("charge", help="charge of the ligand", type=int)
parser.add_argument("params", help="JSON file with advanced parameters",
                    type=argparse.FileType(), nargs='?')

args = parser.parse_args()

pdb_name = '.'.join(args.pdb.name.split('.')[:-1])
ligand_name = args.ligand
ligand_charge = args.charge

params = {
    'antechamber': {
        'ligand': args.ligand,
        'charge': args.charge,
        'ligand_chainID': "L",
        'ligand_index': 1,
    },
    'propka': {
        'with_propka': True,
        'ph': 7.0,
        'ph_offset': 0.7,
    },
    'tleap': {
        'template': 'sphere',
        'solvent_radius': 20.0,
        'solvent_closeness': 0.75,
        'include': []
    }
}

if args.params is not None:
    params = utils.merge_dicts_of_dicts(params, json.load(args.params))
    args.params.close()


print("Starting PREP protocol in {}/".format(pdb_name))

if os.path.exists(pdb_name):
    print("It appears you've already (attempted to) run prep.py with {0}. "
          "Delete folder {0} or rename pdb if you want to run it again."
          .format(pdb_name))
    sys.exit()
utils.set_working_directory(pdb_name)

pdb = pdb_utils.Pdb(args.pdb)

ligands = pdb.get_residues_by_name(ligand_name)
if len(ligands) == 0:
    raise ValueError("No ligands found")

ligand_index = params['antechamber']['ligand_index']
if ligand_index > len(ligands):
    raise ValueError("ligand_index is larger than the number of ligands")

ligand_atoms = ligands[ligand_index-1]
if len(ligands) > 1:
    print("More than one ligand detected. Using coordinates from the ligand"
          " with chainID={} and resSeq={}"
          .format(ligand_atoms[0]['chainID'], ligand_atoms[0]['resSeq']))

# Only generate ligand frcmod if it is not found in include paths
ligand_frcmod = utils.file_in_paths(ligand_name + '.frcmod',
                                    params['tleap']['include'])
antechamber = wrappers.AntechamberWrapper(
    pdb_utils.Pdb(atoms=ligand_atoms), ligand_name, ligand_charge,
    create_frcmod=ligand_frcmod is None
)
if ligand_frcmod is None:
    params['tleap']['include'].append(antechamber.working_directory)

# Change ligand chain ID to ligand_chainID
ligand_chainID = params['antechamber']['ligand_chainID']
pdb_utils.modify_atoms(ligand_atoms, 'chainID', ligand_chainID)

# Run pdb4amber and reduce
reduceResults = wrappers.Pdb4AmberReduceWrapper(pdb)
pdb = reduceResults.pdb
params['tleap']['water_pdb'] = reduceResults.waterPdb

# Run propka31 if requested and found
if params['propka']['with_propka']:
    if shutil.which('propka31'):
        pdb = wrappers.PropkaWrapper(
            pdb,
            ph=params['propka']['ph'],
            ph_offset=params['propka']['ph_offset']
        ).pdb
    else:
        print("propka31 cannot be found in $PATH.\n"
              "WARNING: all ASP/GLU will be treated as unprotonated.")

ligand = pdb.get_residues_by_name(ligand_name)[ligand_index-1]
params['tleap']['name'] = os.path.basename(pdb_name)
params['tleap']['pdb'] = pdb
params['tleap']['ligand'] = ligand
wrappers.TleapWrapper(params['tleap']['template'],
                      params['tleap']['include'],
                      reduceResults.nonprot_residues,
                      params['tleap'])
print("Finished PREP protocol.")

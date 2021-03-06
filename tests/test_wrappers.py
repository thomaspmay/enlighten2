import unittest
import unittest.mock as mock
import wrappers
import pdb_utils
from io import StringIO


def iterable_mock_open(_mock=None, read_data=''):
    """
    Returns modified mock_open object that supports iteration
    (iter, next, etc.)
    """
    mock_open = mock.mock_open(mock=_mock, read_data=read_data)
    mock_open.return_value.__iter__ = lambda self: self
    mock_open.return_value.__next__ = (lambda self:
                                       next(iter(self.readline, '')))
    return mock_open


def setup_mock(mock_os, mock_os_path):
    mock_os_path.exists.return_value = False
    mock_os_path.isfile.return_value = True
    mock_os.environ = {'AMBERHOME': ""}
    mock_os.getcwd.return_value = '.'


class TestAntechamberWrapper(unittest.TestCase):

    @mock.patch('wrappers.utils')
    @mock.patch('wrappers.os.path')
    @mock.patch('wrappers.os')
    def test_antechamber_simple_call(self, mock_os, mock_os_path, mock_utils):
        setup_mock(mock_os, mock_os_path)
        pdb = mock.MagicMock()
        pdb.to_filename = mock.MagicMock()
        antechamber = wrappers.AntechamberWrapper(pdb, 'XXX', 1)

        mock_utils.run_in_shell.assert_has_calls([
            mock.call("/bin/antechamber -i ligand.pdb -fi pdb "
                      "-o XXX.prepc -fo prepc -rn XXX -c bcc -nc 1",
                      'antechamber.out'),
            mock.call(("/bin/parmchk2 -i XXX.prepc -f prepc -o XXX.frcmod"),
                      'parmchk2.out')
        ])


class TestPdb4AmberReduceWrapper(unittest.TestCase):

    @mock.patch('wrappers.utils')
    @mock.patch('wrappers.os.path')
    @mock.patch('wrappers.os')
    def test_pdb4amber_reduce_call(self, mock_os, mock_os_path, mock_utils):
        setup_mock(mock_os, mock_os_path)
        pdb = mock.MagicMock()
        pdb.to_filename = mock.MagicMock()

        # Create a "list" of iterable_mock_open instances to mock properly
        # multiple open() calls in Pdb4AmberReduceWrapper.__init__
        mock_open_files = ['tests/test_files/reduce.pdb',
                           'tests/test_files/pdb4amber_nonprot.pdb',
                           'tests/test_files/pdb4amber_nonprot.pdb']
        mock_open = mock.MagicMock()
        side_effects = []
        for file in mock_open_files:
            with open(file) as f:
                side_effects.append(iterable_mock_open(read_data=f.read())())
        mock_open.side_effect = side_effects

        with mock.patch('wrappers.open', mock_open):
            result = wrappers.Pdb4AmberReduceWrapper(pdb)
        self.assertEqual(len(result.pdb.atoms), 4080)
        self.assertEqual(result.nonprot_residues, {'0RN'})

    def test_get_renamed_histidines(self):
        renamed_histidines = {'A_262_HIS': 'HIE',
                              'A_1_HIS': 'HIE',
                              'A_71_HIS': 'HIE',
                              'A_87_HIS': 'HID',
                              'A_128_HIS': 'HIE',
                              'A_133_HIS': 'HIE'}
        with open('tests/test_files/reduce.pdb') as f:
            reducePdb = pdb_utils.Pdb(f)
        self.assertEqual(wrappers.get_renamed_histidines(reducePdb),
                         renamed_histidines)


class TestPropkaWrapper(unittest.TestCase):

    def test_line_to_pka_entry(self):
        self.assertEqual(
            wrappers.line_to_pka_entry("   ARG 215 A    12.39      12.50    "),
            {'resName': 'ARG',
             'resSeq': 215,
             'chainID': 'A',
             'pKa': 12.39,
             'model-pKa': 12.50}
        )

    def test_parse_propka_output(self):
        with open('tests/test_files/propka.pka') as f:
            output = wrappers.parse_propka_output(f)
        self.assertEqual(len(output), 76)
        self.assertEqual(
            output['A_154_ASP'],
            {'resName': 'ASP',
             'resSeq': 154,
             'chainID': 'A',
             'pKa': 4.24,
             'model-pKa': 3.80}
        )

    @mock.patch('wrappers.utils')
    @mock.patch('wrappers.print')
    @mock.patch('wrappers.os.path')
    @mock.patch('wrappers.os')
    def test_propka_call(self, mock_os, mock_os_path, mock_print, mock_utils):
        setup_mock(mock_os, mock_os_path)

        with open('tests/test_files/reduce.pdb') as f:
            pdb = pdb_utils.Pdb(f)
        pdb.to_filename = mock.MagicMock()

        with open('tests/test_files/propka.pka') as f:
            mock_open = iterable_mock_open(read_data=f.read())

        with mock.patch('wrappers.open', mock_open):
            result = wrappers.PropkaWrapper(pdb)
        residues = result.pdb.residues()

        self.assertEqual(len(result.prot_list), 1)
        self.assertEqual(len(result.deprot_list), 0)
        self.assertNotIn('A_189_ASP', residues)
        self.assertIn('A_189_ASH', residues)
        self.assertEqual(len(residues['A_189_ASH']), 12)


class TestTleapWrapper(unittest.TestCase):

    @mock.patch('wrappers.os.path.isfile')
    def test_get_tleap_includes(self, mock_isfile):
        result = {'loadoff test1/res1.off',
                  'loadamberprep test1/res1.prepc',
                  'loadamberprep test2/res2.prepc',
                  'loadamberparams test1/res1.frcmod',
                  'loadamberparams test2/res2.frcmod'}

        FILES = {'test1': ['res1.off', 'res1.prepc', 'res1.frcmod'],
                 'test2': ['res2.prepc', 'res2.frcmod']}

        def side_effect(path):
            dir, name = path.split('/')
            return name in FILES[dir]
        mock_isfile.side_effect = side_effect

        self.assertEqual(
            set(wrappers.get_tleap_includes(['test1', 'test2'],
                                            ['res1', 'res2']).split('\n')),
            result
        )

        with self.assertRaises(FileNotFoundError) as context:
            wrappers.get_tleap_includes(['test1', 'test2'],
                                        ['res1', 'res3'])
        self.assertEquals(str(context.exception),
                          "Cannot find topology (res3.prepc) "
                          "for residue res3. Exiting...")

    @mock.patch('wrappers.utils')
    @mock.patch('wrappers.os.system')
    @mock.patch('wrappers.get_tleap_includes')
    def test_tleap_call(self, mock_includes, *args):
        pdb = mock.MagicMock()
        pdb.to_filename = mock.MagicMock()
        PARAMS = {'name': 'XXX',
                  'pdb': pdb,
                  'water_pdb': pdb,
                  'solvent_radius': 20.0,
                  'solvent_closeness': 0.75,
                  'ligand': [{'name': "CA",
                              'resSeq': 1}]}
        template_file = StringIO()
        with open('tleap/sphere.in') as f:
            template_file.write(f.read())
        template_file.seek(0)

        generated_input = StringIO()

        def side_effect(data):
            generated_input.write(data)

        mock_includes.return_value = "loadoff XXX.off\nloadamberprep XXX.prepc"
        with mock.patch("builtins.open", mock.mock_open()) as mock_file:
            mock_input = mock.MagicMock()
            mock_input.write = mock.MagicMock()
            mock_input.write.side_effect = side_effect
            mock_file.return_value.__enter__.side_effect = [template_file,
                                                            mock_input]
            with mock.patch("builtins.print", mock.mock_open()) as mock_print:
                wrappers.TleapWrapper('sphere', params=PARAMS)
        generated_input.seek(0)
        with open('tests/test_files/sphere.in') as f:
            self.assertEqual(generated_input.read(), f.read())

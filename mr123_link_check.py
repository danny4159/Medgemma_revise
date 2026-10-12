import warnings
warnings.filterwarnings('ignore')
import pandas as pd
import mr123_labels as m

c = m.load_candidates()
c = c[c.label.isin(['positive', 'negative'])]
B = m.BASE
cols = ['patient_uid', 'study_uid', 'series_id', 'classified_modality', 'is_derived', 'acquisition_plane', 'is_localizer',
        'is_subtraction', 'array_shape', 'array_spacing_mm', 'StudyDescription', 'ProcedureCodeSequence_0_CodeMeaning']
md = pd.concat([pd.read_csv(B + f'metadata/{b}_metadata.csv', low_memory=False, usecols=cols).assign(batch_id=b) for b in m.BATCHES])
print(md.is_localizer.dtype, md.is_derived.dtype)
f = md[(md.classified_modality == 'FLAIR') & (md.acquisition_plane == 'AXIAL') & (md.is_localizer.astype(str) == 'False')
       & (md.is_derived.astype(str) == 'False') & (md.is_subtraction.astype(str) == 'False')]
print(len(f), f.series_id.value_counts().head())
x = c.merge(f.drop(columns=['patient_uid']), on=['batch_id', 'study_uid'])
print(x.groupby(['batch_id', 'label']).study_uid.nunique())
print(x.groupby(['batch_id', 'label']).patient_uid.nunique())
print(x.StudyDescription.value_counts().head(12))
print(x.ProcedureCodeSequence_0_CodeMeaning.value_counts().head(8))
print(x.array_shape.value_counts().head(5))
print(x.array_spacing_mm.head(5).tolist())

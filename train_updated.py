import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader
from torch.nn import CrossEntropyLoss
from transformers import RobertaTokenizer, RobertaForMaskedLM, RobertaConfig, get_linear_schedule_with_warmup
import torch.optim as optim
import joblib
from rdkit import Chem
from rdkit.Chem import AllChem, DataStructs
import numpy as np

# Load the dataset
file_path = 'entire file path'
data_org = pd.read_csv(file_path)

# Custom dataset class
class SMILESDataset(Dataset):
    def __init__(self, df, tokenizer, max_length=128):
        self.df = df
        self.tokenizer = tokenizer
        self.max_length = max_length

    def __len__(self):
        return len(self.df)

    def __getitem__(self, idx):
        drug_smiles = self.df.iloc[idx]['DRUG SMILES']
        fragment_smiles = self.df.iloc[idx]['FRAG_SMILES']

        inputs = self.tokenizer(drug_smiles, max_length=self.max_length, padding='max_length', truncation=True, return_tensors="pt")
        inputs = {key: val.squeeze(0) for key, val in inputs.items()}
        
        fragment_inputs = self.tokenizer(fragment_smiles, max_length=self.max_length, padding='max_length', truncation=True, return_tensors="pt")
        fragment_ids = fragment_inputs['input_ids'].squeeze(0)

        labels = fragment_ids.clone()
        
        return {
            **inputs,
            'labels': labels,
            'actual_fragment_smiles': fragment_smiles
        }

# Initialize tokenizer and model
tokenizer = RobertaTokenizer.from_pretrained('seyonec/ChemBERTa-zinc-base-v1')
config = RobertaConfig.from_pretrained('seyonec/ChemBERTa-zinc-base-v1')
model = RobertaForMaskedLM.from_pretrained('seyonec/ChemBERTa-zinc-base-v1', config=config)

# Create dataset and dataloader
dataset = SMILESDataset(data_org, tokenizer)
dataloader = DataLoader(dataset, batch_size=1, shuffle=True)

# Define optimizer, loss function, and learning rate scheduler
optimizer = optim.AdamW(model.parameters(), lr=5e-5)
total_steps = len(dataloader) * 10  # 10 epochs
scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=0, num_training_steps=total_steps)
loss_fn = CrossEntropyLoss()

# Training loop
model.train()
for epoch in range(10):  # 10 epochs
    for batch in dataloader:
        optimizer.zero_grad()
        
        outputs = model(input_ids=batch['input_ids'], attention_mask=batch['attention_mask'], labels=batch['labels'])
        loss = outputs.loss
        
        loss.backward()
        optimizer.step()
        scheduler.step()

        print(f"Epoch: {epoch}, Loss: {loss.item()}")

# Save the trained model and tokenizer
model.save_pretrained('enter file paths')
tokenizer.save_pretrained('/Users/nisargshah/Documents/cs/ml4/frag_ml/tokenizer')
joblib.dump(config, 'entire file path/config.pkl')

# Function to calculate Tanimoto similarity
def tanimoto_similarity(smiles1, smiles2):
    mol1 = Chem.MolFromSmiles(smiles1)
    mol2 = Chem.MolFromSmiles(smiles2)
    
    if mol1 is None or mol2 is None:
        return 0.0
    
    fp1 = AllChem.GetMorganFingerprintAsBitVect(mol1, 2, nBits=2048)
    fp2 = AllChem.GetMorganFingerprintAsBitVect(mol2, 2, nBits=2048)
    
    return DataStructs.TanimotoSimilarity(fp1, fp2)

# Evaluation
true_values = []
predicted_values = []
tanimoto_similarities = []

model.eval()
with torch.no_grad():
    for batch in dataloader:
        outputs = model(input_ids=batch['input_ids'], attention_mask=batch['attention_mask'], labels=batch['labels'])
        predictions = outputs.logits.argmax(dim=-1)

        # Decode the predicted SMILES and the actual SMILES
        predicted_smiles = tokenizer.decode(predictions[0], skip_special_tokens=True)
        actual_smiles = batch['actual_fragment_smiles'][0]

        true_values.append(actual_smiles)
        predicted_values.append(predicted_smiles)

        # Calculate Tanimoto similarity
        similarity = tanimoto_similarity(actual_smiles, predicted_smiles)
        tanimoto_similarities.append(similarity)

# Calculate mean Tanimoto similarity
mean_tanimoto_similarity = np.mean(tanimoto_similarities)

print(f"Mean Tanimoto Similarity: {mean_tanimoto_similarity}")

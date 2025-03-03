import pandas as pd
import json

file_path = "./local_samples.pkl"

local_sample_df = pd.read_pickle(file_path)
start_index = 175

for index, row in local_sample_df.iterrows():
    if index < start_index:
        continue

    print("\n" + "="*80)
    print(f"Row {index} of {len(local_sample_df)-1}")
    print(f"Task ID: {row['id']}")
    print(f"Goal: {row['goal']}")
    print(f"Language: {row['language']}")
    print(f"Plan: {json.dumps(row['plan'], indent=4, ensure_ascii=False)}")
    
    while True:
        response = input("\nIs this valid? (Y/N/quit to exit): ").strip().lower()
        if response in ['y', 'n', 'quit']:
            break
        print("Please enter Y, N, or quit")
    
    if response == 'quit':
        print("Exiting review process...")
        break
        
    local_sample_df.at[index, 'is_valid'] = (response != 'n')
    
    if index % 10 == 0:
        local_sample_df.to_pickle(file_path)
        print("Progress saved...")


local_sample_df.to_pickle(file_path)
print("\nReview complete. Final results saved.")

valid_count = local_sample_df['is_valid'].sum()
total_count = len(local_sample_df)
print(f"\nSummary:")
print(f"Total rows reviewed: {total_count}")
print(f"Valid rows: {valid_count}")
print(f"Invalid rows: {total_count - valid_count}")
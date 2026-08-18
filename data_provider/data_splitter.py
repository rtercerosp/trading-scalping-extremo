import pandas as pd
from typing import Tuple

class DataSplitter:
    """
    A class to split a pandas DataFrame chronologically into Train, Test, and Validation sets.
    The splitting is strictly sequential to prevent look-ahead bias.
    """

    def __init__(self, train_ratio: float = 0.7, test_ratio: float = 0.15, validation_ratio: float = 0.15):
        """
        Initializes the DataSplitter with specified ratios for each dataset.

        Args:
            train_ratio (float): Proportion of data for the training set.
            test_ratio (float): Proportion of data for the testing set.
            validation_ratio (float): Proportion of data for the validation set.

        Raises:
            ValueError: If the sum of ratios is not approximately 1.0.
        """
        if not (0.99 <= (train_ratio + test_ratio + validation_ratio) <= 1.01):
            raise ValueError("The sum of train_ratio, test_ratio, and validation_ratio must be approximately 1.0.")
        if not all(0 <= r <= 1 for r in [train_ratio, test_ratio, validation_ratio])):
            raise ValueError("Ratios must be between 0 and 1.")

        self.train_ratio = train_ratio
        self.test_ratio = test_ratio
        self.validation_ratio = validation_ratio

    def split_data(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Splits the input DataFrame chronologically into Train, Test, and Validation sets.

        Args:
            df (pd.DataFrame): The input DataFrame to be split. It is assumed to be
                               already sorted chronologically.

        Returns:
            Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]: A tuple containing
                                                             (train_df, test_df, validation_df).
        """
        if df.empty:
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

        total_rows = len(df)

        train_end_index = int(total_rows * self.train_ratio)
        test_end_index = int(total_rows * (self.train_ratio + self.test_ratio))

        train_df = df.iloc[:train_end_index]
        test_df = df.iloc[train_end_index:test_end_index]
        validation_df = df.iloc[test_end_index:]

        return train_df, test_df, validation_df

# Example usage (optional, for testing purposes)
if __name__ == "__main__":
    # Create a sample DataFrame
    data = {'timestamp': pd.to_datetime(pd.date_range(start='2023-01-01', periods=100, freq='H')),
            'value': range(100)}
    sample_df = pd.DataFrame(data)
    sample_df = sample_df.set_index('timestamp')

    print("Original DataFrame head:")
    print(sample_df.head())
    print("\nOriginal DataFrame tail:")
    print(sample_df.tail())
    print(f"\nTotal rows: {len(sample_df)}")

    # Initialize splitter
    splitter = DataSplitter(train_ratio=0.7, test_ratio=0.15, validation_ratio=0.15)

    # Split data
    train_set, test_set, validation_set = splitter.split_data(sample_df)

    print(f"\nTrain set rows: {len(train_set)}")
    print(f"Test set rows: {len(test_set)}")
    print(f"Validation set rows: {len(validation_set)}")

    print("\nTrain set head:")
    print(train_set.head())
    print("\nTrain set tail:")
    print(train_set.tail())

    print("\nTest set head:")
    print(test_set.head())
    print("\nTest set tail:")
    print(test_set.tail())

    print("\nValidation set head:")
    print(validation_set.head())
    print("\nValidation set tail:")
    print(validation_set.tail())

    # Verify chronological order
    print(f"\nLast train timestamp: {train_set.index[-1] if not train_set.empty else 'N/A'}")
    print(f"First test timestamp: {test_set.index[0] if not test_set.empty else 'N/A'}")
    print(f"Last test timestamp: {test_set.index[-1] if not test_set.empty else 'N/A'}")
    print(f"First validation timestamp: {validation_set.index[0] if not validation_set.empty else 'N/A'}")

    # Test with different ratios
    print("\n--- Testing with custom ratios (60/20/20) ---")
    splitter_custom = DataSplitter(train_ratio=0.6, test_ratio=0.2, validation_ratio=0.2)
    train_c, test_c, val_c = splitter_custom.split_data(sample_df)
    print(f"Train set rows (custom): {len(train_c)}")
    print(f"Test set rows (custom): {len(test_c)}")
    print(f"Validation set rows (custom): {len(val_c)}")

    # Test with empty DataFrame
    print("\n--- Testing with empty DataFrame ---")
    empty_df = pd.DataFrame(columns=['timestamp', 'value'])
    empty_train, empty_test, empty_val = splitter.split_data(empty_df)
    print(f"Empty train rows: {len(empty_train)}")
    print(f"Empty test rows: {len(empty_test)}")
    print(f"Empty validation rows: {len(empty_val)}")
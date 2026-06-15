import numpy as np

def get_criteria_from_pois(
    pois_gdf,
    amenity_col
):

    criteria = (
        pois_gdf[amenity_col]
        .dropna()
        .unique()
        .tolist()
    )

    return criteria


def build_pairwise_matrix(criteria):

    n = len(criteria)
    matrix = np.ones((n, n))
    total_comparisons = (n * (n - 1))/2
    comparison_count = 0

    for i in range(n):
        for j in range(i + 1, n):

            comparison_count += 1

            print(f"\n[{comparison_count}/{int(total_comparisons)}] Comparing:")
            print(f"1. {criteria[i]}")
            print(f"2. {criteria[j]}")
            print("3. Equal importance")

            choice = input("Which is more important? (1/2/3): ")

            if choice == "3":
                score = 1

            else:
                score = int(
                    input(
                        "Importance level "
                        "(1,3,5,7,9): "
                    )
                )

            if choice == "1":
                matrix[i, j] = score
                matrix[j, i] = 1 / score

            elif choice == "2":
                matrix[i, j] = 1 / score
                matrix[j, i] = score

            else:
                matrix[i, j] = 1
                matrix[j, i] = 1

    return matrix


def calculate_ahp_weights(matrix):

    eigenvalues, eigenvectors = np.linalg.eig(matrix)

    max_index = np.argmax(eigenvalues.real)

    weights = eigenvectors[:, max_index].real

    weights = weights / weights.sum()

    return weights


def calculate_consistency_ratio(matrix):

    RI_TABLE = {
        1: 0.00,
        2: 0.00,
        3: 0.58,
        4: 0.90,
        5: 1.12,
        6: 1.24,
        7: 1.32,
        8: 1.41,
        9: 1.45,
        10: 1.49
    }

    n = matrix.shape[0]

    eigenvalues, _ = np.linalg.eig(matrix)
    lambda_max = np.max(eigenvalues.real)

    ci = (lambda_max - n) / (n - 1)

    ri = RI_TABLE.get(n)

    if ri == 0:
        return 0

    cr = ci / ri

    return cr


def run_ahp(
    pois_gdf,
    amenity_col
):

    criteria = get_criteria_from_pois(
        pois_gdf,
        amenity_col
    )

    print("\nCriteria:")
    for c in criteria:
        print(f"- {c}")

    print(
        "\nPlease define the relative importance between each criterion."
        "\n\nSaaty's Scale:"
        "\n1 = Equal importance"
        "\n3 = Moderate importance"
        "\n5 = Strong importance"
        "\n7 = Very strong importance"
        "\n9 = Extreme importance"
    )

    matrix = build_pairwise_matrix(criteria)
    weights = calculate_ahp_weights(matrix)
    cr = calculate_consistency_ratio(matrix)

    weight_dict = {
        criteria[i]: round(float(weights[i]),3)
        for i in range(len(criteria))
    }

    return {
        "criteria": criteria,
        "matrix": matrix,
        "weights": weight_dict,
        "consistency_ratio": cr
    }



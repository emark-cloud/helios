// SPDX-License-Identifier: GPL-3.0
/*
    Copyright 2021 0KIMS association.

    This file is generated with [snarkJS](https://github.com/iden3/snarkjs).

    snarkJS is a free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    snarkJS is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
    or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
    License for more details.

    You should have received a copy of the GNU General Public License
    along with snarkJS. If not, see <https://www.gnu.org/licenses/>.
*/

pragma solidity >=0.7.0 <0.9.0;

contract MomentumV1Verifier {
    // Scalar field size
    uint256 constant r =
        21_888_242_871_839_275_222_246_405_745_257_275_088_548_364_400_416_034_343_698_204_186_575_808_495_617;
    // Base field size
    uint256 constant q =
        21_888_242_871_839_275_222_246_405_745_257_275_088_696_311_157_297_823_662_689_037_894_645_226_208_583;

    // Verification Key data
    uint256 constant alphax =
        20_491_192_805_390_485_299_153_009_773_594_534_940_189_261_866_228_447_918_068_658_471_970_481_763_042;
    uint256 constant alphay =
        9_383_485_363_053_290_200_918_347_156_157_836_566_562_967_994_039_712_273_449_902_621_266_178_545_958;
    uint256 constant betax1 =
        4_252_822_878_758_300_859_123_897_981_450_591_353_533_073_413_197_771_768_651_442_665_752_259_397_132;
    uint256 constant betax2 =
        6_375_614_351_688_725_206_403_948_262_868_962_793_625_744_043_794_305_715_222_011_528_459_656_738_731;
    uint256 constant betay1 =
        21_847_035_105_528_745_403_288_232_691_147_584_728_191_162_732_299_865_338_377_159_692_350_059_136_679;
    uint256 constant betay2 =
        10_505_242_626_370_262_277_552_901_082_094_356_697_409_835_680_220_590_971_873_171_140_371_331_206_856;
    uint256 constant gammax1 =
        11_559_732_032_986_387_107_991_004_021_392_285_783_925_812_861_821_192_530_917_403_151_452_391_805_634;
    uint256 constant gammax2 =
        10_857_046_999_023_057_135_944_570_762_232_829_481_370_756_359_578_518_086_990_519_993_285_655_852_781;
    uint256 constant gammay1 =
        4_082_367_875_863_433_681_332_203_403_145_435_568_316_851_327_593_401_208_105_741_076_214_120_093_531;
    uint256 constant gammay2 =
        8_495_653_923_123_431_417_604_973_247_489_272_438_418_190_587_263_600_148_770_280_649_306_958_101_930;
    uint256 constant deltax1 =
        11_037_986_455_866_761_586_831_234_964_326_163_300_859_471_176_845_307_294_950_268_639_022_229_604_979;
    uint256 constant deltax2 =
        16_480_185_906_596_315_538_263_341_739_043_108_542_184_468_353_670_912_222_822_891_164_533_880_113_286;
    uint256 constant deltay1 =
        21_655_460_724_166_367_528_139_057_185_515_940_864_158_290_838_194_582_496_847_604_058_883_819_227_782;
    uint256 constant deltay2 =
        9_054_246_101_977_590_758_229_139_666_090_443_093_513_619_142_872_411_249_589_812_887_980_075_193_209;

    uint256 constant IC0x =
        17_928_457_527_648_076_711_430_893_571_740_962_748_777_099_656_287_242_178_664_053_578_750_143_752_077;
    uint256 constant IC0y =
        19_656_144_775_436_227_865_216_321_954_297_834_174_975_435_395_495_645_653_729_071_112_288_687_109_114;

    uint256 constant IC1x =
        6_584_014_632_959_326_939_247_249_861_086_168_991_731_605_806_184_170_126_836_393_416_430_218_881_351;
    uint256 constant IC1y =
        2_601_902_423_160_677_860_083_126_732_348_696_677_055_458_803_614_701_632_728_543_551_191_017_625_912;

    uint256 constant IC2x =
        13_452_505_596_321_764_957_805_103_409_137_712_014_463_123_543_824_526_433_824_545_987_901_791_356_204;
    uint256 constant IC2y =
        17_712_715_021_827_440_142_685_674_882_486_902_654_207_792_212_316_532_959_308_545_733_753_338_319_727;

    uint256 constant IC3x =
        8_969_131_654_086_879_903_181_474_838_479_194_891_496_976_839_974_147_696_255_682_273_945_988_733_431;
    uint256 constant IC3y =
        16_119_787_224_827_613_074_961_852_017_444_869_089_853_714_213_760_917_053_850_112_500_180_016_821_770;

    uint256 constant IC4x =
        14_059_627_232_423_980_097_164_949_131_006_003_232_256_448_682_218_695_993_028_177_742_132_178_454_927;
    uint256 constant IC4y =
        4_097_737_291_654_077_767_323_685_509_762_140_975_570_954_099_639_393_028_838_338_767_979_695_021_351;

    uint256 constant IC5x =
        21_419_154_735_388_049_015_038_042_238_581_463_092_941_579_882_089_008_420_982_515_083_173_008_558_940;
    uint256 constant IC5y =
        3_716_813_457_572_382_568_269_083_487_925_201_563_779_288_052_133_197_106_643_988_456_331_161_803_854;

    uint256 constant IC6x =
        6_793_842_501_509_910_827_163_800_062_739_083_698_492_415_903_811_919_194_484_942_316_838_417_850_270;
    uint256 constant IC6y =
        17_326_140_140_306_527_001_200_006_909_815_751_859_413_401_385_451_104_827_269_659_517_299_243_412_918;

    uint256 constant IC7x =
        18_737_066_456_399_647_194_561_314_012_426_614_583_286_557_017_351_381_325_460_312_945_104_149_628_336;
    uint256 constant IC7y =
        9_108_426_947_515_026_168_153_979_016_417_188_192_372_092_235_653_352_598_176_022_021_021_336_822_159;

    uint256 constant IC8x =
        16_858_953_601_558_602_081_005_970_177_014_924_110_396_838_977_303_681_385_054_616_750_689_601_699_537;
    uint256 constant IC8y =
        6_121_749_561_515_429_056_656_758_375_643_370_971_040_732_378_215_807_582_759_268_706_224_095_240_219;

    uint256 constant IC9x =
        21_344_097_603_397_731_808_384_004_353_693_916_886_292_557_305_145_430_125_442_439_420_162_948_948_961;
    uint256 constant IC9y =
        15_478_985_141_083_507_633_929_112_049_728_674_951_204_140_988_975_775_811_929_361_613_438_518_026_317;

    uint256 constant IC10x =
        7_909_455_985_740_948_493_660_672_374_639_289_795_965_971_887_142_094_670_051_293_084_652_099_989_902;
    uint256 constant IC10y =
        11_202_002_372_860_523_138_564_772_986_160_083_959_076_496_327_206_134_731_493_364_492_220_735_890_528;

    uint256 constant IC11x =
        15_377_325_947_592_459_729_508_322_422_207_299_094_025_292_065_637_919_678_952_479_555_416_792_908_731;
    uint256 constant IC11y =
        15_299_116_727_785_358_417_586_574_518_458_500_690_959_205_913_516_277_977_718_127_900_802_349_813_135;

    // Memory data
    uint16 constant pVk = 0;
    uint16 constant pPairing = 128;

    uint16 constant pLastMem = 896;

    function verifyProof(
        uint256[2] calldata _pA,
        uint256[2][2] calldata _pB,
        uint256[2] calldata _pC,
        uint256[11] calldata _pubSignals
    ) public view returns (bool) {
        assembly {
            function checkField(v) {
                if iszero(lt(v, r)) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            // G1 function to multiply a G1 value(x,y) to value in an address
            function g1_mulAccC(pR, x, y, s) {
                let success
                let mIn := mload(0x40)
                mstore(mIn, x)
                mstore(add(mIn, 32), y)
                mstore(add(mIn, 64), s)

                success := staticcall(sub(gas(), 2000), 7, mIn, 96, mIn, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }

                mstore(add(mIn, 64), mload(pR))
                mstore(add(mIn, 96), mload(add(pR, 32)))

                success := staticcall(sub(gas(), 2000), 6, mIn, 128, pR, 64)

                if iszero(success) {
                    mstore(0, 0)
                    return(0, 0x20)
                }
            }

            function checkPairing(pA, pB, pC, pubSignals, pMem) -> isOk {
                let _pPairing := add(pMem, pPairing)
                let _pVk := add(pMem, pVk)

                mstore(_pVk, IC0x)
                mstore(add(_pVk, 32), IC0y)

                // Compute the linear combination vk_x

                g1_mulAccC(_pVk, IC1x, IC1y, calldataload(add(pubSignals, 0)))

                g1_mulAccC(_pVk, IC2x, IC2y, calldataload(add(pubSignals, 32)))

                g1_mulAccC(_pVk, IC3x, IC3y, calldataload(add(pubSignals, 64)))

                g1_mulAccC(_pVk, IC4x, IC4y, calldataload(add(pubSignals, 96)))

                g1_mulAccC(_pVk, IC5x, IC5y, calldataload(add(pubSignals, 128)))

                g1_mulAccC(_pVk, IC6x, IC6y, calldataload(add(pubSignals, 160)))

                g1_mulAccC(_pVk, IC7x, IC7y, calldataload(add(pubSignals, 192)))

                g1_mulAccC(_pVk, IC8x, IC8y, calldataload(add(pubSignals, 224)))

                g1_mulAccC(_pVk, IC9x, IC9y, calldataload(add(pubSignals, 256)))

                g1_mulAccC(_pVk, IC10x, IC10y, calldataload(add(pubSignals, 288)))

                g1_mulAccC(_pVk, IC11x, IC11y, calldataload(add(pubSignals, 320)))

                // -A
                mstore(_pPairing, calldataload(pA))
                mstore(add(_pPairing, 32), mod(sub(q, calldataload(add(pA, 32))), q))

                // B
                mstore(add(_pPairing, 64), calldataload(pB))
                mstore(add(_pPairing, 96), calldataload(add(pB, 32)))
                mstore(add(_pPairing, 128), calldataload(add(pB, 64)))
                mstore(add(_pPairing, 160), calldataload(add(pB, 96)))

                // alpha1
                mstore(add(_pPairing, 192), alphax)
                mstore(add(_pPairing, 224), alphay)

                // beta2
                mstore(add(_pPairing, 256), betax1)
                mstore(add(_pPairing, 288), betax2)
                mstore(add(_pPairing, 320), betay1)
                mstore(add(_pPairing, 352), betay2)

                // vk_x
                mstore(add(_pPairing, 384), mload(add(pMem, pVk)))
                mstore(add(_pPairing, 416), mload(add(pMem, add(pVk, 32))))

                // gamma2
                mstore(add(_pPairing, 448), gammax1)
                mstore(add(_pPairing, 480), gammax2)
                mstore(add(_pPairing, 512), gammay1)
                mstore(add(_pPairing, 544), gammay2)

                // C
                mstore(add(_pPairing, 576), calldataload(pC))
                mstore(add(_pPairing, 608), calldataload(add(pC, 32)))

                // delta2
                mstore(add(_pPairing, 640), deltax1)
                mstore(add(_pPairing, 672), deltax2)
                mstore(add(_pPairing, 704), deltay1)
                mstore(add(_pPairing, 736), deltay2)

                let success := staticcall(sub(gas(), 2000), 8, _pPairing, 768, _pPairing, 0x20)

                isOk := and(success, mload(_pPairing))
            }

            let pMem := mload(0x40)
            mstore(0x40, add(pMem, pLastMem))

            // Validate that all evaluations ∈ F

            checkField(calldataload(add(_pubSignals, 0)))

            checkField(calldataload(add(_pubSignals, 32)))

            checkField(calldataload(add(_pubSignals, 64)))

            checkField(calldataload(add(_pubSignals, 96)))

            checkField(calldataload(add(_pubSignals, 128)))

            checkField(calldataload(add(_pubSignals, 160)))

            checkField(calldataload(add(_pubSignals, 192)))

            checkField(calldataload(add(_pubSignals, 224)))

            checkField(calldataload(add(_pubSignals, 256)))

            checkField(calldataload(add(_pubSignals, 288)))

            checkField(calldataload(add(_pubSignals, 320)))

            // Validate all evaluations
            let isValid := checkPairing(_pA, _pB, _pC, _pubSignals, pMem)

            mstore(0, isValid)
            return(0, 0x20)
        }
    }
}
